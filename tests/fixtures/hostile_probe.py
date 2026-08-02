"""Hostile builder probing every route a review named.

Lives under tests/ because it deliberately attempts to reach question and gold files from
inside a memory build. It must never be importable from shipped code.
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any

REPO = "/public/home/wwb/KE_mem/ke-memory-demo"
GOLD = (
    f"{REPO}/.worktrees/e2e-closure-20260730/research/next-prep/artifacts/"
    "natural-benchmark-slices/slice-v1/gold.json"
)


def _first_hit(root: str, name: str, depth: int = 4) -> str | None:
    """Bounded search, so the probe cannot hang on a large tree."""
    root_depth = root.rstrip("/").count("/")
    for current, dirs, files in os.walk(root):
        if current.count("/") - root_depth >= depth:
            dirs[:] = []
            continue
        dirs[:] = [d for d in dirs if not d.startswith((".venv", "__pycache__", ".git"))]
        if name in files:
            return os.path.join(current, name)
    return None


def tries_everything(build_input: dict[str, Any]) -> dict[str, Any]:
    found: dict[str, Any] = {}

    found["via_sys_path"] = [
        hit
        for entry in sys.path
        if entry and os.path.isdir(entry)
        for hit in [_first_hit(entry, "gold.json", depth=3)]
        if hit
    ][:2]

    parent = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    found["via_file_parent"] = _first_hit(parent, "gold.json", depth=4)

    found["known_absolute_readable"] = os.path.exists(GOLD)
    if found["known_absolute_readable"]:
        try:
            with open(GOLD, encoding="utf-8") as fh:
                found["gold_items_read"] = len(json.load(fh)["items"])
        except Exception as exc:
            found["gold_items_read"] = f"blocked: {type(exc).__name__}"

    try:
        found["proc_self_fd"] = len(os.listdir("/proc/self/fd"))
    except Exception as exc:
        found["proc_self_fd"] = f"blocked: {type(exc).__name__}"

    found["repo_visible"] = os.path.isdir(REPO)
    found["home_visible"] = os.path.isdir("/public/home/wwb")
    return found
