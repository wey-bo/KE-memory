"""Immutable raw-output and sidecar storage for AMR pilot attempts."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path

from tools.amr_pilot.models import AttemptSidecar


@dataclass(frozen=True, slots=True)
class StoredAttempt:
    raw_path: Path
    sidecar_path: Path
    raw_sha256: str
    sidecar_sha256: str


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _basename(sidecar: AttemptSidecar) -> str:
    return f"{sidecar.sample_id}-{sidecar.route}-attempt-{sidecar.attempt}"


def _sidecar_content(sidecar: AttemptSidecar) -> bytes:
    value = sidecar.model_dump(mode="json")
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _load_sidecar(path: Path) -> AttemptSidecar:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"could not read previous attempt sidecar: {error}") from error
    return AttemptSidecar.model_validate(value)


def write_attempt(
    run_directory: str | Path,
    raw_output: str,
    sidecar: AttemptSidecar,
) -> StoredAttempt:
    root = Path(run_directory)
    raw_bytes = raw_output.encode("utf-8")
    raw_sha256 = _sha256_bytes(raw_bytes)
    if raw_sha256 != sidecar.raw_output_sha256:
        raise ValueError("raw_output_sha256 does not match raw output")

    if sidecar.attempt == 2:
        first_base = f"{sidecar.sample_id}-{sidecar.route}-attempt-1"
        first_path = root / "sidecar" / f"{first_base}.json"
        if not first_path.exists():
            raise ValueError("attempt 1 is missing")
        first_hash = _sha256_bytes(first_path.read_bytes())
        if sidecar.previous_attempt_sha256 != first_hash:
            raise ValueError("previous_attempt_sha256 does not match attempt 1 sidecar")
        first = _load_sidecar(first_path)
        if first.parse_status != "invalid":
            raise ValueError("attempt 2 requires an attempt 1 parse failure")

    base = _basename(sidecar)
    raw_path = root / "raw" / f"{base}.txt"
    sidecar_path = root / "sidecar" / f"{base}.json"
    if raw_path.exists() or sidecar_path.exists():
        raise ValueError(f"refusing to overwrite immutable attempt: {base}")

    sidecar_bytes = _sidecar_content(sidecar)
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    sidecar_path.parent.mkdir(parents=True, exist_ok=True)
    with raw_path.open("xb") as output:
        output.write(raw_bytes)
    with sidecar_path.open("xb") as output:
        output.write(sidecar_bytes)
    return StoredAttempt(
        raw_path=raw_path,
        sidecar_path=sidecar_path,
        raw_sha256=raw_sha256,
        sidecar_sha256=_sha256_bytes(sidecar_bytes),
    )
