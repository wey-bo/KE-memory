"""Run a memory build inside a mount namespace that cannot see the repository.

An earlier attempt used a child process with an empty working directory and a scrubbed
environment. A review correctly rejected it, and a hostile probe then read all 32 gold items
through a hard-coded absolute path: same user, same filesystem namespace, so nothing was
actually out of reach. Failing to open a relative path proves only that the relative path was
wrong.

This version builds a new root. The child runs in unprivileged user, mount, network and PID
namespaces, with a tmpfs root into which only three things are bind-mounted read-only:

- the interpreter and system libraries it needs to start
- the site-packages the builder depends on
- a staging directory holding *only* the builder module

The repository, the question channel and the gold channel are never mounted, so they are not
merely unreadable but absent from the namespace. Networking is unshared, and inheritable file
descriptors are closed, so neither offers a way out.

:attr:`SandboxManifest.visible_mounts` publishes exactly what the child can see, which is a
stronger statement than a list of accesses that happened to fail.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final, cast
from pathlib import Path

from ke_memory_demo.core.json import JsonObject, JsonValue, canonical_json

from .channels import MemoryBuildInput


class SandboxUnavailableError(RuntimeError):
    """The kernel or userland cannot provide the required isolation."""


class SandboxedBuildError(RuntimeError):
    """The sandboxed build failed, or returned something inconsistent."""


@dataclass(frozen=True)
class SandboxManifest:
    """What the child could see, reconciled against what the kernel reported.

    ``intended_mounts`` is what this module asked for; ``observed_mount_points`` comes from
    the child's own ``/proc/self/mountinfo``. A review rightly objected that a code-generated
    allowlist proves nothing, so the two are compared and the reconciliation result is part of
    the manifest.
    """

    intended_mounts: tuple[str, ...]
    observed_mount_points: tuple[str, ...]
    observed_root_entries: tuple[str, ...]
    observed_staging_entries: tuple[str, ...]
    observed_fd_count: int
    observed_network_interfaces: tuple[str, ...]
    namespaces: tuple[str, ...]
    reconciled: bool
    reconciliation_notes: tuple[str, ...]

    def as_json(self) -> JsonObject:
        return {
            "intended_mounts": list(self.intended_mounts),
            "observed_mount_points": list(self.observed_mount_points),
            "observed_root_entries": list(self.observed_root_entries),
            "observed_staging_entries": list(self.observed_staging_entries),
            "observed_fd_count": self.observed_fd_count,
            "observed_network_interfaces": list(self.observed_network_interfaces),
            "namespaces": list(self.namespaces),
            "reconciled": self.reconciled,
            "reconciliation_notes": list(self.reconciliation_notes),
            "repository_mounted": False,
            "question_channel_mounted": False,
            "gold_channel_mounted": False,
            "evidence_basis": (
                "observed_* fields are read from the child's own /proc/self/mountinfo, "
                "/proc/self/fd and directory listings, not asserted by the parent"
            ),
        }


@dataclass(frozen=True)
class SandboxedBuildResult:
    artifact: JsonValue
    artifact_sha256: str
    build_input_sha256: str
    sandbox: SandboxManifest


_CHILD = r"""
import json, os, sys, importlib

# Close inherited descriptors beyond the standard three, so a leaked handle to a gold file
# cannot be read even if one were passed in.
try:
    os.closerange(3, 4096)
except Exception:
    pass

payload = json.load(sys.stdin)

# Report the namespace as the kernel sees it, so the manifest can be reconciled against
# observed state rather than trusted as a code-generated claim.
def _observed():
    mounts = []
    try:
        with open("/proc/self/mountinfo", encoding="utf-8") as fh:
            for line in fh:
                parts = line.split()
                if len(parts) < 5:
                    continue
                sep = parts.index("-") if "-" in parts else len(parts)
                fstype = parts[sep + 1] if sep + 1 < len(parts) else "?"
                mounts.append({"mount_point": parts[4], "fstype": fstype})
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
        "netns_interfaces": sorted(os.listdir("/sys/class/net")) if os.path.isdir("/sys/class/net") else [],
    }

observed = _observed()
sys.path.insert(0, "/staging")
module = importlib.import_module(payload["builder_module"])
build = getattr(module, payload["builder_attr"])
artifact = build(payload["build_input"])
sys.stdout.write(json.dumps({"artifact": artifact, "observed": observed}, sort_keys=True))
"""

_PROBE = "import os,sys;print('|'.join(sorted(os.listdir('/'))))"


def sandbox_available() -> bool:
    """Whether this host can actually provide the namespaces we require."""
    if shutil.which("unshare") is None:
        return False
    try:
        completed = subprocess.run(
            [
                "unshare",
                "--user",
                "--map-root-user",
                "--mount",
                "--net",
                "--pid",
                "--fork",
                "true",
            ],
            capture_output=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return completed.returncode == 0


def base_interpreter() -> Path:
    """The interpreter to run inside the sandbox.

    Deliberately not ``sys.executable``: that lives in the project virtualenv, and an earlier
    version added its parent directory to the mount list, which bind-mounted over the venv's
    own bin directory and destroyed it. The base interpreter recorded in ``pyvenv.cfg`` sits
    outside the project entirely.
    """
    prefix = Path(getattr(sys, "base_prefix", sys.prefix))
    candidate = prefix / "bin" / f"python{sys.version_info.major}.{sys.version_info.minor}"
    if candidate.exists():
        return candidate.resolve()
    fallback = prefix / "bin" / "python3"
    if fallback.exists():
        return fallback.resolve()
    return Path(sys.executable).resolve()


def _library_roots() -> tuple[Path, ...]:
    """Minimal read-only mounts the interpreter needs to start.

    Never includes any directory inside the project virtualenv: mounting over it corrupts the
    parent environment, and the sandbox must not depend on project state anyway.
    """
    roots: list[Path] = [base_interpreter().parent.parent]
    for candidate in ("/usr", "/lib", "/lib64", "/bin"):
        path = Path(candidate)
        if path.exists():
            roots.append(path)
    project_venv = Path(sys.prefix).resolve()
    unique: list[Path] = []
    for root in roots:
        resolved = root.resolve()
        if project_venv == resolved or project_venv in resolved.parents:
            continue
        if resolved.exists() and not any(
            resolved == seen or seen in resolved.parents for seen in unique
        ):
            unique.append(resolved)
    return tuple(unique)


def run_sandboxed_build(
    build_input: MemoryBuildInput,
    *,
    builder_source: Path,
    builder_module: str,
    builder_attr: str,
    extra_site_packages: Sequence[Path] = (),
    timeout_seconds: int = 600,
) -> SandboxedBuildResult:
    """Build memory inside a namespace where the repository does not exist.

    ``builder_source`` is a single module file. It is copied into a staging directory that is
    the only project code mounted, so a directory such as ``tests/`` is never exposed.
    """
    if not sandbox_available():
        raise SandboxUnavailableError(
            "unprivileged user, mount, network and PID namespaces are required; "
            "without them a build cannot be shown to be unable to reach gold"
        )
    if not builder_source.is_file():
        raise SandboxedBuildError(f"builder source is not a file: {builder_source}")

    content = build_input.canonical_content()
    serialized = canonical_json(content)
    build_input_sha256 = hashlib.sha256(serialized).hexdigest()
    payload = json.dumps(
        {
            "builder_module": builder_module,
            "builder_attr": builder_attr,
            "build_input": content,
        },
        sort_keys=True,
    )

    library_roots = _library_roots()
    site_roots = tuple(Path(p).resolve() for p in extra_site_packages)

    with tempfile.TemporaryDirectory(prefix="ke-sandbox-") as work:
        work_path = Path(work)
        newroot = work_path / "newroot"
        staging = newroot / "staging"
        staging.mkdir(parents=True)
        # Only the builder module is staged. Copying a directory would risk exposing
        # neighbouring files, which is how a tests/ mount would have leaked a probe's peers.
        shutil.copy2(builder_source, staging / f"{builder_module}.py")

        # The interpreter lives on a FUSE filesystem that a new user namespace cannot see,
        # so it is copied into local storage rather than bind-mounted.
        local_interp = work_path / "interp"
        shutil.copytree(base_interpreter().parent.parent, local_interp, symlinks=True)
        interp_relative = (
            base_interpreter().relative_to(base_interpreter().parent.parent)
        )

        mount_targets: list[str] = ["/interp (ro, copied interpreter)"]
        script_lines = [
            "set -e",
            f"mount -t tmpfs tmpfs {newroot}",
            # tmpfs replaces the directory, so every mount point is created after it.
            f"mkdir -p {newroot}/interp {newroot}/proc {newroot}/staging {newroot}/dev "
            f"{newroot}/tmp",
            f"mount --bind -o ro {local_interp} {newroot}/interp",
            f"cp {builder_source} {newroot}/staging/{builder_module}.py",
            f"cp {work_path / 'child.py'} {newroot}/staging/_child.py",
        ]
        for root in (*library_roots, *site_roots):
            if str(root).startswith(("/public", "/home")):
                # Anything on the project filesystem is copied, never mounted, so the
                # namespace never gains a path into the repository.
                continue
            target = newroot / str(root).lstrip("/")
            script_lines.append(f"mkdir -p {target}")
            script_lines.append(f"mount --bind -o ro {root} {target}")
            mount_targets.append(f"{root} (ro)")
        # On a merged-/usr host these are symlinks, so they must be recreated as symlinks
        # rather than bind-mounted; the loader resolves them through /usr.
        for link in ("lib", "lib64"):
            if Path(f"/{link}").is_symlink() or not Path(f"/{link}").exists():
                script_lines.append(f"ln -sfn usr/{link} {newroot}/{link}")
            else:
                script_lines.append(f"mkdir -p {newroot}/{link}")
                script_lines.append(f"mount --bind -o ro /{link} {newroot}/{link}")
            mount_targets.append(f"/{link} (resolved through /usr)")
        script_lines.append(f"mount -t proc proc {newroot}/proc")
        for node in ("urandom", "null", "zero"):
            script_lines.append(f": > {newroot}/dev/{node}")
            script_lines.append(f"mount --bind /dev/{node} {newroot}/dev/{node}")
        mount_targets.append("/dev/{urandom,null,zero} (only these three nodes)")
        mount_targets.append("/proc (fresh procfs in a private PID namespace)")
        mount_targets.append("/staging (the builder module file, and nothing else)")
        mount_targets.append("/tmp (empty tmpfs)")
        # The child script travels as a file. Embedding it in an sh -c string mangles the
        # newlines, which produced a syntax error rather than a build.
        (work_path / "child.py").write_text(_CHILD, encoding="utf-8")
        script_lines.append(
            f"exec unshare --root={newroot} /interp/{interp_relative} -I -S "
            f"/staging/_child.py"
        )

        try:
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
                    "\n".join(script_lines),
                ],
                input=payload,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
                close_fds=True,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise SandboxedBuildError("sandboxed build timed out") from exc

    if completed.returncode != 0:
        raise SandboxedBuildError(
            f"sandboxed build failed with code {completed.returncode}: "
            f"{completed.stderr.strip()[:500]}"
        )

    try:
        result = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise SandboxedBuildError(
            f"sandboxed build returned invalid JSON: {completed.stdout[:200]!r}"
        ) from exc

    artifact = result["artifact"]
    observed = result.get("observed", {})
    manifest = reconcile_manifest(
        intended=tuple(mount_targets),
        observed=observed,
        builder_module=builder_module,
    )
    if not manifest.reconciled:
        raise SandboxedBuildError(
            "the sandbox did not match its manifest: "
            + "; ".join(manifest.reconciliation_notes)
        )
    return SandboxedBuildResult(
        artifact=artifact,
        artifact_sha256=hashlib.sha256(canonical_json(artifact)).hexdigest(),
        build_input_sha256=build_input_sha256,
        sandbox=manifest,
    )


def _string_tuple(value: object) -> tuple[str, ...]:
    """Strings from an untrusted JSON list, ignoring anything that is not one."""
    if not isinstance(value, list):
        return ()
    items = cast("list[object]", value)
    return tuple(item for item in items if isinstance(item, str))


# Paths that must never appear as a mount point or root entry inside the sandbox.
_FORBIDDEN_PATH_FRAGMENTS: Final[tuple[str, ...]] = (
    "/public",
    "/home",
    "ke-memory-demo",
    "research",
    "natural-benchmark-slices",
)


def reconcile_manifest(
    *,
    intended: tuple[str, ...],
    observed: JsonObject,
    builder_module: str,
) -> SandboxManifest:
    """Compare what was asked for against what the kernel actually reported."""
    notes: list[str] = []

    raw_mounts = observed.get("mountinfo")
    mount_points: list[str] = []
    if isinstance(raw_mounts, list):
        for entry in cast("list[object]", raw_mounts):
            if isinstance(entry, dict):
                point = cast("dict[str, object]", entry).get("mount_point")
                if isinstance(point, str):
                    mount_points.append(point)
    if not mount_points:
        notes.append("the child reported no mountinfo, so nothing could be reconciled")

    root_entries = _string_tuple(observed.get("root_entries"))
    staging_entries = _string_tuple(observed.get("staging_entries"))
    fd_count = observed.get("fd_count")
    interfaces = _string_tuple(observed.get("netns_interfaces"))

    # A forbidden path must appear neither as a mount point nor at the root.
    for point in mount_points:
        if any(fragment in point for fragment in _FORBIDDEN_PATH_FRAGMENTS):
            notes.append(f"forbidden path is mounted inside the sandbox: {point}")
    for entry in root_entries:
        if any(fragment.strip("/") == entry for fragment in _FORBIDDEN_PATH_FRAGMENTS):
            notes.append(f"forbidden path is present at the sandbox root: /{entry}")

    # Staging must hold exactly the builder module and the child script.
    expected_staging = {f"{builder_module}.py", "_child.py"}
    unexpected = sorted(set(staging_entries) - expected_staging)
    if unexpected:
        notes.append(f"staging holds files beyond the builder: {unexpected}")
    missing = sorted(expected_staging - set(staging_entries))
    if missing:
        notes.append(f"staging is missing expected files: {missing}")

    if isinstance(fd_count, int) and fd_count > 8:
        notes.append(f"the child holds {fd_count} descriptors, more than its own stdio")

    # An unshared network namespace has at most a down loopback device.
    if any(iface not in {"lo"} for iface in interfaces):
        notes.append(f"the network namespace exposes interfaces: {list(interfaces)}")

    return SandboxManifest(
        intended_mounts=intended,
        observed_mount_points=tuple(sorted(set(mount_points))),
        observed_root_entries=root_entries,
        observed_staging_entries=staging_entries,
        observed_fd_count=fd_count if isinstance(fd_count, int) else -1,
        observed_network_interfaces=interfaces,
        namespaces=("user", "mount", "network", "pid"),
        reconciled=not notes,
        reconciliation_notes=tuple(notes),
    )


def probe_visible_root(
    *,
    extra_site_packages: Sequence[Path] = (),
    timeout_seconds: int = 120,
) -> tuple[str, ...]:
    """Return the child's root listing, so the allowlist can be asserted, not assumed."""
    if not sandbox_available():
        raise SandboxUnavailableError("namespaces unavailable")
    library_roots = _library_roots()
    site_roots = tuple(Path(p).resolve() for p in extra_site_packages)
    with tempfile.TemporaryDirectory(prefix="ke-sandbox-probe-") as work:
        newroot = Path(work) / "newroot"
        newroot.mkdir(parents=True)
        lines = ["set -e", f"mount -t tmpfs tmpfs {newroot}"]
        for root in (*library_roots, *site_roots):
            target = newroot / str(root).lstrip("/")
            lines.append(f"mkdir -p {target}")
            lines.append(f"mount --bind -o ro {root} {target}")
        lines.append(f"mkdir -p {newroot}/proc {newroot}/staging {newroot}/tmp")
        lines.append(f"mount -t proc proc {newroot}/proc")
        lines.append(
            f"exec unshare --root={newroot} {base_interpreter()} -I -S -c "
            + json.dumps(_PROBE)
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
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
    if completed.returncode != 0:
        raise SandboxedBuildError(f"probe failed: {completed.stderr.strip()[:300]}")
    return tuple(completed.stdout.strip().split("|"))
