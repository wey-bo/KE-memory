"""Freeze the three third-party ontology sources at their pinned versions.

Writes ``artifacts/ontology-sources/{wordnet,propbank,schemaorg}.json`` plus a
``source-freeze.json`` manifest holding one independent sha256 per source.

This script does not download. The raw archives live under
``/public/home/wwb/datasets/ontology-sources`` (outside the repository, since they total
~16 MB), were fetched once via the commands recorded in each pin, and are verified against
those recorded digests on every run. Keeping the freeze offline means a re-run reproduces
the same artifacts instead of silently picking up a newer upstream release.

A source that is missing, or whose bytes do not match its pin, is written into the manifest
as ``unavailable`` with the command that would fetch it. That is a real outcome to report,
not a crash: the reviewable fact is which sources are backed by verified bytes.

No model call and no judge call is made; parsing local files is the whole of the work.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import cast

from ke_memory_demo.core.json import JsonObject
from ke_memory_demo.ontology_sources import (
    MANIFEST_NAME,
    RAW_ROOT,
    SourceFreezeEntry,
    freeze_sources,
    snapshot_sha256,
)
from ke_memory_demo.ontology_sources.models import HASH_SCOPE

ARTIFACT_DIR = Path("artifacts/ontology-sources")


def _write(path: Path, payload: JsonObject) -> None:
    with path.open("w", encoding="utf-8") as stream:
        json.dump(payload, stream, indent=2, ensure_ascii=False, sort_keys=True)
        stream.write("\n")


def main() -> int:
    frozen = freeze_sources(RAW_ROOT)
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)

    for name, snapshot in sorted(frozen.snapshots.items()):
        payload = cast(JsonObject, snapshot.model_dump(mode="json"))
        # The freeze block travels inside the artifact so whoever opens wordnet.json can
        # re-derive the digest from the file alone: drop this block, canonicalise, hash.
        payload["freeze"] = {
            "source": name,
            "sha256": snapshot_sha256(snapshot),
            "hash_scope": HASH_SCOPE,
        }
        _write(ARTIFACT_DIR / f"{name}.json", payload)

    _write(
        ARTIFACT_DIR / MANIFEST_NAME,
        cast(JsonObject, frozen.manifest.model_dump(mode="json")),
    )

    print("three independent source hashes (no combined hash, by design):")
    for name, digest in sorted(frozen.manifest.digests().items()):
        print(f"  {name:<12} {digest}")

    for entry in frozen.manifest.entries:
        if isinstance(entry, SourceFreezeEntry):
            counts = ", ".join(f"{k}={v}" for k, v in sorted(entry.parsed_counts.items()))
            print(f"{entry.source.value}: acquired {entry.acquisition.resolved_version}")
            print(f"  raw sha256 {entry.acquisition.raw_sha256}")
            print(f"  raw bytes  {entry.acquisition.raw_bytes} at {entry.acquisition.raw_path}")
            print(f"  licence    {entry.acquisition.licence}")
            print(f"  parsed     {counts}")
        else:
            print(f"{entry.source.value}: UNAVAILABLE -- {entry.failure_mode}")
            for command in entry.commands_tried:
                print(f"  tried: {command}")

    unavailable = frozen.manifest.unavailable()
    print(f"sources acquired: {len(frozen.snapshots)} of 3; unavailable: {len(unavailable)}")
    print("judge dependency: none; no model or judge call was made")
    print(f"artifacts: {ARTIFACT_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
