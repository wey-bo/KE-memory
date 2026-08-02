"""Stand-in memory builder, imported by the isolated build child process.

Receives the serialized build input as plain JSON. It has no access to questions or gold,
and no path to them: the child runs outside the repository with nothing on argv.
"""

from __future__ import annotations

from typing import Any


def build_memory(build_input: dict[str, Any]) -> dict[str, Any]:
    conversations = build_input["conversations"]
    return {
        "conversations": len(conversations),
        "handles": {
            c["conversation_handle"]: [
                t["evidence_handle"] for s in c["sessions"] for t in s["turns"]
            ]
            for c in conversations
        },
        "turn_count": sum(len(s["turns"]) for c in conversations for s in c["sessions"]),
    }
