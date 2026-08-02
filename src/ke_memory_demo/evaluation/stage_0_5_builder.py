"""Memory builder, imported by the isolated build child process.

Receives the serialized build input as plain JSON. It has no access to questions or gold and no
path to them: the child runs in a namespace where the repository does not exist.

It emits a handle-addressable index with a per-turn content digest. The earlier version returned
a conversation count and a turn count, which nothing downstream could consume, so the chain was
disconnected in the middle while still recording an artifact hash.

Deliberately dependency-free: only this file is staged into the sandbox, so it cannot import from
``ke_memory_demo``. The digest formula is duplicated from
``ke_memory_demo.evaluation.memory_artifact.turn_digest`` and a test asserts the two agree, which
is the price of the isolation being real.
"""

from __future__ import annotations

import hashlib
from typing import Any

BUILDER_ID = "stage-2-handle-index-builder"
BUILDER_VERSION = "1"


def turn_content_digest(speaker: str, text: str) -> str:
    return hashlib.sha256(f"{speaker}\x00{text}".encode()).hexdigest()


def build_memory(build_input: dict[str, Any]) -> dict[str, Any]:
    """Index the build input into an artifact later layers can actually read."""
    conversations: list[dict[str, Any]] = []
    session_members: dict[str, list[str]] = {}

    for conversation in build_input["conversations"]:
        session_handles: list[str] = []
        turns: list[dict[str, Any]] = []
        for session in conversation["sessions"]:
            session_handle = str(session["session_handle"])
            session_handles.append(session_handle)
            members: list[str] = []
            for turn in session["turns"]:
                handle = str(turn["evidence_handle"])
                speaker = str(turn.get("speaker", "unknown"))
                text = str(turn.get("text", ""))
                members.append(handle)
                turns.append(
                    {
                        "evidence_handle": handle,
                        "session_handle": session_handle,
                        "speaker": speaker,
                        "text": text,
                        "approximate_tokens": int(turn.get("approximate_tokens", 0)),
                        "content_sha256": turn_content_digest(speaker, text),
                    }
                )
            session_members[session_handle] = members

        if turns:
            conversations.append(
                {
                    "conversation_handle": str(conversation["conversation_handle"]),
                    "session_handles": session_handles,
                    "turns": turns,
                }
            )

    return {
        "builder_id": BUILDER_ID,
        "builder_version": BUILDER_VERSION,
        # Binds the artifact to the input it was built from, so a consumer can detect an artifact
        # built from different content.
        "build_input_sha256": str(build_input.get("build_input_sha256", "unbound")),
        "conversations": conversations,
        "session_members": session_members,
    }
