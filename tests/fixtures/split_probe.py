"""Analysis probes for the split-isolation boundary.

``tries_to_reach_other_splits`` deliberately attempts to open sibling split files, which is the
access an id-declaration convention could not prevent. Lives under tests/ so it is never
importable from shipped code.
"""

from __future__ import annotations

import glob
import os
from typing import Any

SPLIT_NAMES = ("held_out.json", "validation.json", "discovery.json")


def honest(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "split": payload["split"],
        "questions": len(payload["questions"]),
        "gold": len(payload["gold"]),
    }


def tries_to_reach_other_splits(payload: dict[str, Any]) -> dict[str, Any]:
    found: dict[str, Any] = {"own_split": payload["split"]}
    hits: list[str] = []
    for name in SPLIT_NAMES:
        hits += glob.glob(f"/**/{name}", recursive=False)
        for root in ("/", "/tmp", "/staging"):
            candidate = os.path.join(root, name)
            if os.path.exists(candidate):
                hits.append(candidate)
    found["sibling_files_reachable"] = hits
    found["repo_visible"] = os.path.isdir("/public/home/wwb/KE_mem")
    # The only gold present is this split's own, which is the point.
    found["own_gold_count"] = len(payload["gold"])
    return found
