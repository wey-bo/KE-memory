"""Regressions for round-four findings: build isolation, digest binding, opaque handles.

Each corresponds to a demonstrated defeat of the previous implementation:

- a legitimate-looking builder read 32 questions and 32 answers through a closure while the
  freeze receipt still validated, because everything lived in one process
- replacing a turn's text left ``content_digest()`` unchanged, so the receipt bound nothing
  about content
- handles such as ``slice-BEAM-100K-C001-abstention-001`` told a builder the benchmark, the
  conversation and the question category outright
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ke_memory_demo.core.json import JsonObject
from ke_memory_demo.evaluation.channels import (
    ChannelError,
    HandleMint,
    MemoryBuildInput,
    PublicConversation,
    PublicSession,
    PublicTurn,
    assert_handles_are_opaque,
)
from ke_memory_demo.evaluation.sandboxed_build import (
    reconcile_manifest,
    run_sandboxed_build,
    sandbox_available,
)

# Only this single file is staged into the sandbox, never the fixtures directory: mounting a
# directory would expose its neighbours, which is what an earlier extra_import_roots argument
# effectively did.
HOSTILE_PROBE = Path(__file__).resolve().parents[2] / "fixtures" / "hostile_probe.py"

requires_sandbox = pytest.mark.skipif(
    not sandbox_available(),
    reason="unprivileged user, mount, network and PID namespaces are unavailable",
)


def _turn(handle: str = "h00000", text: str = "original bytes", speaker: str = "user", tokens: int = 2) -> PublicTurn:
    return PublicTurn(
        evidence_handle=handle, speaker=speaker, text=text, approximate_tokens=tokens
    )


def _build_input(
    turns: tuple[PublicTurn, ...] | None = None,
    session_metadata: JsonObject | None = None,
    conversation_metadata: JsonObject | None = None,
    conversation_handle: str = "c00000",
    session_handle: str = "s00000",
    extra_conversations: tuple[PublicConversation, ...] = (),
) -> MemoryBuildInput:
    return MemoryBuildInput(
        conversations=(
            PublicConversation(
                conversation_handle=conversation_handle,
                sessions=(
                    PublicSession(
                        session_handle=session_handle,
                        turns=turns or (_turn(),),
                        metadata=session_metadata or {"public_session_ordinal": 0},
                    ),
                ),
                metadata=conversation_metadata or {},
            ),
            *extra_conversations,
        ),
    )


def test_digest_moves_when_any_content_field_changes() -> None:
    """The previous digest hashed only handles, so a text tamper was invisible."""
    baseline = _build_input().content_digest()
    assert len(baseline) == 64

    two_turns = (_turn("h00000", "first"), _turn("h00001", "second"))
    mutations = {
        "turn_text": _build_input((_turn(text="tampered bytes"),)),
        "turn_speaker": _build_input((_turn(speaker="assistant"),)),
        "turn_tokens": _build_input((_turn(tokens=3),)),
        "turn_handle": _build_input((_turn(handle="h00099"),)),
        "session_metadata": _build_input(session_metadata={"public_session_ordinal": 1}),
        "conversation_metadata": _build_input(conversation_metadata={"turn_count": 1}),
        "conversation_handle": _build_input(conversation_handle="c00099"),
        "session_handle": _build_input(session_handle="s00099"),
        # A field added to the tree must move the digest.
        "turn_added": _build_input(two_turns),
        # So must reordering an array while keeping the same members.
        "turn_order_reversed": _build_input(tuple(reversed(two_turns))),
        # And so must adding a whole conversation.
        "conversation_added": _build_input(
            extra_conversations=(
                PublicConversation(
                    conversation_handle="c00001",
                    sessions=(
                        PublicSession(
                            session_handle="s00001",
                            turns=(_turn("h00002", "other"),),
                            metadata={"public_session_ordinal": 0},
                        ),
                    ),
                ),
            )
        ),
    }
    unchanged = [
        field
        for field, mutated in mutations.items()
        if mutated.content_digest() == baseline
    ]
    assert unchanged == [], f"digest did not move for: {unchanged}"

    # Array order must also distinguish the two two-turn inputs from each other, not merely
    # each from the single-turn baseline.
    assert (
        mutations["turn_added"].content_digest()
        != mutations["turn_order_reversed"].content_digest()
    )


def test_digest_is_stable_for_identical_content() -> None:
    assert _build_input().content_digest() == _build_input().content_digest()


def test_handles_must_be_opaque() -> None:
    """A handle carrying dataset or category text is refused."""
    assert_handles_are_opaque(_build_input())

    leaking = MemoryBuildInput(
        conversations=(
            PublicConversation(
                conversation_handle="slice-BEAM-100K-C001-abstention-001",
                sessions=(
                    PublicSession(
                        session_handle="s00000",
                        turns=(
                            PublicTurn(
                                evidence_handle="h00000",
                                speaker="user",
                                text="x",
                                approximate_tokens=1,
                            ),
                        ),
                        metadata={"public_session_ordinal": 0},
                    ),
                ),
            ),
        ),
    )
    with pytest.raises(ChannelError, match="opaque"):
        assert_handles_are_opaque(leaking)


def test_handle_mint_is_stable_and_reversible() -> None:
    mint = HandleMint()
    first = mint.mint("conversation", "slice-BEAM-100K-C001-abstention-001")
    again = mint.mint("conversation", "slice-BEAM-100K-C001-abstention-001")
    assert first == again
    assert mint.source_for(first) == "slice-BEAM-100K-C001-abstention-001"
    # The opaque form carries no dataset text.
    assert "BEAM" not in first and "abstention" not in first


@requires_sandbox
def test_a_hostile_builder_cannot_reach_the_repository_or_gold() -> None:
    """The finding: a builder read all 32 gold items through a hard-coded absolute path.

    An empty working directory and a scrubbed environment did not prevent that, because the
    child shared the filesystem namespace. This probe attempts every route the review named:
    sys.path entries, walking up from __file__, a known absolute path, and /proc/self/fd.
    """
    result = run_sandboxed_build(
        _build_input(),
        builder_source=HOSTILE_PROBE,
        builder_module="hostile_probe",
        builder_attr="tries_everything",
    )
    artifact = result.artifact
    assert isinstance(artifact, dict)
    assert artifact["repo_visible"] is False
    assert artifact["home_visible"] is False
    assert artifact["known_absolute_readable"] is False
    assert artifact["via_sys_path"] == []
    assert artifact["via_file_parent"] is None
    # Only the child's own stdio pipes.
    assert int(str(artifact["proc_self_fd"])) <= 4
    assert "gold_items_read" not in artifact


@requires_sandbox
def test_sandbox_publishes_a_visibility_allowlist() -> None:
    """A list of what is visible is a stronger claim than a list of failed accesses."""
    result = run_sandboxed_build(
        _build_input(),
        builder_source=HOSTILE_PROBE,
        builder_module="hostile_probe",
        builder_attr="tries_everything",
    )
    manifest = result.sandbox.as_json()
    assert manifest["repository_mounted"] is False
    assert manifest["question_channel_mounted"] is False
    assert manifest["gold_channel_mounted"] is False
    assert manifest["reconciled"] is True
    assert set(result.sandbox.namespaces) == {"user", "mount", "network", "pid"}
    # Both the intended list and the observed list must be free of project paths.
    combined = " ".join(
        (*result.sandbox.intended_mounts, *result.sandbox.observed_mount_points)
    )
    assert "/public" not in combined
    assert len(result.build_input_sha256) == 64
    assert result.build_input_sha256 == _build_input().content_digest()


@requires_sandbox
def test_manifest_reconciles_against_the_kernels_own_mountinfo() -> None:
    """A code-generated allowlist proves nothing, so it is checked against observed state."""
    result = run_sandboxed_build(
        _build_input(),
        builder_source=HOSTILE_PROBE,
        builder_module="hostile_probe",
        builder_attr="tries_everything",
    )
    manifest = result.sandbox
    assert manifest.reconciled is True
    assert manifest.reconciliation_notes == ()
    # Read from the child's /proc/self/mountinfo, not asserted by the parent.
    assert manifest.observed_mount_points
    assert not any("/public" in point for point in manifest.observed_mount_points)
    assert "public" not in manifest.observed_root_entries
    # Exactly the builder and the child script.
    assert set(manifest.observed_staging_entries) == {"hostile_probe.py", "_child.py"}
    assert manifest.observed_fd_count <= 4
    assert manifest.observed_network_interfaces == ()


def test_reconciliation_detects_each_violation_class() -> None:
    """The check must not be vacuous, so each failure mode is exercised directly."""
    clean: JsonObject = {
        "mountinfo": [{"mount_point": "/usr", "fstype": "ext4"}],
        "root_entries": ["usr"],
        "staging_entries": ["b.py", "_child.py"],
        "fd_count": 4,
        "netns_interfaces": [],
    }
    assert reconcile_manifest(intended=("/usr",), observed=clean, builder_module="b").reconciled

    violations: dict[str, JsonObject] = {
        "forbidden mount": {
            **clean,
            "mountinfo": [{"mount_point": "/public/home/wwb", "fstype": "fuse"}],
        },
        "forbidden root entry": {**clean, "root_entries": ["usr", "public"]},
        "extra staging file": {
            **clean,
            "staging_entries": ["b.py", "_child.py", "secrets.py"],
        },
        "missing staging file": {**clean, "staging_entries": ["b.py"]},
        "leaked descriptors": {**clean, "fd_count": 40},
        "network interface": {**clean, "netns_interfaces": ["eth0"]},
        "no mountinfo at all": {},
    }
    accepted = [
        name
        for name, observed in violations.items()
        if reconcile_manifest(intended=("/usr",), observed=observed, builder_module="b").reconciled
    ]
    assert accepted == [], f"reconciliation accepted: {accepted}"


def test_sandbox_unavailability_is_not_silently_tolerated() -> None:
    """A skipped test must never stand in for a passing production gate."""
    from ke_memory_demo.evaluation.sandboxed_build import SandboxUnavailableError

    assert issubclass(SandboxUnavailableError, RuntimeError)
    # The production path calls sandbox_available() and refuses; it does not degrade to an
    # in-process build, which is what made the previous implementation defeatable.
    script = (
        Path(__file__).resolve().parents[3] / "scripts" / "stage_0_5_harness_validation.py"
    ).read_text(encoding="utf-8")
    assert "if not sandbox_available():" in script
    assert "return 1" in script.split("if not sandbox_available():")[1][:400]
