from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from tools.natural_memory_benchmark.identity_proposer_policy import (
    IdentityProposerPolicyFreeze,
    freeze_identity_proposer_policy,
    prepare_identity_dev_slice,
)
from tools.natural_memory_benchmark.io import (
    canonical_json_bytes,
    load_json,
    sha256_file,
)


V2_SOURCE = Path(
    "artifacts/identity-memory-experiment/natural-v2/source-cases.json"
)
V3_POLICY_FREEZE = Path(
    "artifacts/identity-memory-experiment/dev-repair-v3/policy-freeze-v3.json"
)
V4_DEV_PUBLIC = Path(
    "artifacts/identity-memory-experiment/dev-repair-v4/public.json"
)
WORKSPACE_ROOT = Path(".")
DEV_CASE_IDS = [
    "case-885f16a65bfdf569",
    "case-113fe134d194132b",
    "case-5dd81a8cec34c956",
    "case-80034c4a6c11c571",
    "case-105e39b70808e864",
    "case-1ed6f84bc0c6914f",
]
SLICE_FILES = (
    "source-cases.json",
    "public.json",
    "authority.json",
    "gold.json",
    "manifest.json",
)


def _run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "tools.natural_memory_benchmark.cli", *args],
        check=True,
        capture_output=True,
        text=True,
    )


def _write_policy(path: Path) -> str:
    text = (
        "For identity, merge only with explicit same-entity evidence.\n"
        "Same thread, topic, or concept is insufficient; otherwise abstain.\n"
    )
    path.write_text(text, encoding="utf-8")
    path.chmod(0o444)
    return text


def test_prepare_identity_dev_slice_keeps_only_v2_dev_cases(tmp_path):
    root = tmp_path / "dev-repair-v3"
    first = prepare_identity_dev_slice(
        V2_SOURCE,
        root,
        workspace_root=WORKSPACE_ROOT,
    )
    first_bytes = {name: (root / name).read_bytes() for name in SLICE_FILES}
    second = prepare_identity_dev_slice(
        V2_SOURCE,
        root,
        workspace_root=WORKSPACE_ROOT,
    )

    public = load_json(root / "public.json")
    source = load_json(root / "source-cases.json")
    assert first == second
    assert first_bytes == {name: (root / name).read_bytes() for name in SLICE_FILES}
    assert first["dataset_id"] == "natural-identity-membership-dev-repair-v3"
    assert first["case_count"] == 6
    assert first["dev_count"] == 6
    assert first["hidden_count"] == 0
    assert [case["case_id"] for case in public["cases"]] == DEV_CASE_IDS
    assert {case["split"] for case in public["cases"]} == {"dev"}
    assert [case["case_id"] for case in source["cases"]] == DEV_CASE_IDS
    assert all((root / name).stat().st_mode & 0o777 == 0o444 for name in SLICE_FILES)


def test_prepare_identity_dev_slice_rejects_substituted_v2_semantics(tmp_path):
    substituted_source = tmp_path / "source-cases.json"
    payload = load_json(V2_SOURCE)
    payload["cases"][0]["question"] = "Substituted dev-only training semantics"
    substituted_source.write_bytes(canonical_json_bytes(payload))
    substituted_source.chmod(0o444)

    with pytest.raises(ValueError, match="frozen opaque v2 source"):
        prepare_identity_dev_slice(
            substituted_source,
            tmp_path / "dev-repair-v3",
            workspace_root=WORKSPACE_ROOT,
        )


def test_freeze_policy_binds_same_bytes_into_both_prompts(tmp_path):
    dev_root = tmp_path / "dev-repair-v3"
    prepare_identity_dev_slice(V2_SOURCE, dev_root, workspace_root=WORKSPACE_ROOT)
    policy_path = tmp_path / "policy-v1.md"
    policy_text = _write_policy(policy_path)
    dev_prompt = tmp_path / "dev-prompt.md"
    final_prompt = tmp_path / "final-prompt.md"
    freeze_path = tmp_path / "policy-freeze.json"
    future_public = tmp_path / "natural-v3-fresh" / "public.json"

    first = freeze_identity_proposer_policy(
        policy_path,
        dev_prompt,
        final_prompt,
        freeze_path,
        dev_public_path=dev_root / "public.json",
        final_public_path=future_public,
        dev_run_id="run-dev-policy-v1",
        final_run_id="run-fresh-v3",
        proposer_id="codex-gpt-5.6-sol",
        proposer_version="2026-07-27-policy-v1",
    )
    second = freeze_identity_proposer_policy(
        policy_path,
        dev_prompt,
        final_prompt,
        freeze_path,
        dev_public_path=dev_root / "public.json",
        final_public_path=future_public,
        dev_run_id="run-dev-policy-v1",
        final_run_id="run-fresh-v3",
        proposer_id="codex-gpt-5.6-sol",
        proposer_version="2026-07-27-policy-v1",
    )

    assert first == second
    assert first["policy_sha256"] == sha256_file(policy_path)
    assert first["dev_public_sha256"] == sha256_file(dev_root / "public.json")
    assert first["fresh_hidden_authored_before_policy_freeze"] is False
    assert first["final_public_path"] == str(future_public.resolve())
    assert first["dev_prompt_sha256"] == sha256_file(dev_prompt)
    assert first["final_prompt_sha256"] == sha256_file(final_prompt)
    for prompt, public_path, run_id, case_count in (
        (dev_prompt, dev_root / "public.json", "run-dev-policy-v1", 6),
        (final_prompt, future_public, "run-fresh-v3", 12),
    ):
        content = prompt.read_text(encoding="utf-8")
        assert policy_text in content
        assert sha256_file(policy_path) in content
        assert str(public_path.resolve()) in content
        assert run_id in content
        assert f"`case_count`: `{case_count}`" in content
        assert prompt.stat().st_mode & 0o777 == 0o444
    assert freeze_path.stat().st_mode & 0o777 == 0o444


def test_policy_freeze_model_keeps_v3_defaults_backward_compatible():
    frozen = IdentityProposerPolicyFreeze.model_validate(load_json(V3_POLICY_FREEZE))

    assert frozen.dev_dataset_id == "natural-identity-membership-dev-repair-v3"
    assert frozen.dev_case_count == 6
    assert frozen.final_case_count == 12


def test_freeze_policy_supports_v4_dataset_and_variable_case_counts(tmp_path):
    policy_path = tmp_path / "policy-v4.md"
    policy_text = _write_policy(policy_path)
    dev_prompt = tmp_path / "dev-prompt-v4.md"
    final_prompt = tmp_path / "final-prompt-v4.md"
    freeze_path = tmp_path / "policy-freeze-v4.json"
    future_public = tmp_path / "natural-v4-fresh" / "public.json"

    frozen = freeze_identity_proposer_policy(
        policy_path,
        dev_prompt,
        final_prompt,
        freeze_path,
        dev_public_path=V4_DEV_PUBLIC,
        final_public_path=future_public,
        dev_run_id="run-dev-policy-v4",
        final_run_id="run-fresh-v4",
        proposer_id="codex-gpt-5.6-sol",
        proposer_version="2026-07-28-policy-v4",
        dev_dataset_id="natural-identity-membership-dev-repair-v4",
        dev_case_count=12,
        final_case_count=6,
    )

    assert frozen["dev_dataset_id"] == "natural-identity-membership-dev-repair-v4"
    assert frozen["dev_case_count"] == 12
    assert frozen["final_case_count"] == 6
    for prompt, public_path, run_id, case_count in (
        (dev_prompt, V4_DEV_PUBLIC, "run-dev-policy-v4", 12),
        (final_prompt, future_public, "run-fresh-v4", 6),
    ):
        content = prompt.read_text(encoding="utf-8")
        assert policy_text in content
        assert str(public_path.resolve()) in content
        assert run_id in content
        assert f"`case_count`: `{case_count}`" in content


def test_freeze_policy_accepts_writable_input_and_rejects_conflicting_replay(tmp_path):
    """A writable policy is accepted; a conflicting replay is not.

    The first phase previously required the policy to be mode 0444 and expected
    "policy must be read-only". Git preserves no write bit, so a policy arrives
    writable from any clone and that precondition could never hold. The protection
    that matters is the second phase: re-freezing with different bytes is refused,
    which is what actually keeps a frozen policy immutable.
    """
    dev_root = tmp_path / "dev-repair-v3"
    prepare_identity_dev_slice(V2_SOURCE, dev_root, workspace_root=WORKSPACE_ROOT)
    policy_path = tmp_path / "policy-v1.md"
    policy_path.write_text("abstain without explicit evidence\n", encoding="utf-8")
    assert policy_path.stat().st_mode & 0o222, "precondition: writable, as after a clone"

    dev_prompt = tmp_path / "dev-prompt.md"
    final_prompt = tmp_path / "final-prompt.md"
    freeze_path = tmp_path / "policy-freeze.json"
    freeze_identity_proposer_policy(
        policy_path,
        dev_prompt,
        final_prompt,
        freeze_path,
        dev_public_path=dev_root / "public.json",
        final_public_path=tmp_path / "future-public.json",
        dev_run_id="run-dev-policy-v1",
        final_run_id="run-fresh-v3",
        proposer_id="codex-gpt-5.6-sol",
        proposer_version="2026-07-27-policy-v1",
    )
    dev_prompt.chmod(0o644)
    dev_prompt.write_text("conflicting prompt\n", encoding="utf-8")
    with pytest.raises(FileExistsError, match="immutable artifact differs"):
        freeze_identity_proposer_policy(
            policy_path,
            dev_prompt,
            final_prompt,
            freeze_path,
            dev_public_path=dev_root / "public.json",
            final_public_path=tmp_path / "future-public.json",
            dev_run_id="run-dev-policy-v1",
            final_run_id="run-fresh-v3",
            proposer_id="codex-gpt-5.6-sol",
            proposer_version="2026-07-27-policy-v1",
        )


def test_cli_prepares_dev_slice_and_freezes_policy(tmp_path):
    dev_root = tmp_path / "dev-repair-v3"
    prepared = _run_cli(
        "prepare-identity-dev-slice",
        "--v2-source",
        str(V2_SOURCE),
        "--output-root",
        str(dev_root),
        "--workspace-root",
        ".",
    )
    assert '"case_count": 6' in prepared.stdout

    policy_path = tmp_path / "policy-v1.md"
    _write_policy(policy_path)
    frozen = _run_cli(
        "freeze-identity-proposer-policy",
        "--policy",
        str(policy_path),
        "--dev-prompt",
        str(tmp_path / "dev-prompt.md"),
        "--final-prompt",
        str(tmp_path / "final-prompt.md"),
        "--output",
        str(tmp_path / "policy-freeze.json"),
        "--dev-public",
        str(dev_root / "public.json"),
        "--final-public",
        str(tmp_path / "natural-v3-fresh" / "public.json"),
        "--dev-run-id",
        "run-dev-policy-v1",
        "--final-run-id",
        "run-fresh-v3",
        "--proposer-id",
        "codex-gpt-5.6-sol",
        "--proposer-version",
        "2026-07-27-policy-v1",
    )
    assert '"status": "frozen"' in frozen.stdout
    assert '"fresh_hidden_authored_before_policy_freeze": false' in frozen.stdout


def test_cli_freezes_v4_policy_with_variable_case_counts(tmp_path):
    policy_path = tmp_path / "policy-v4.md"
    _write_policy(policy_path)
    frozen = _run_cli(
        "freeze-identity-proposer-policy",
        "--policy",
        str(policy_path),
        "--dev-prompt",
        str(tmp_path / "dev-prompt-v4.md"),
        "--final-prompt",
        str(tmp_path / "final-prompt-v4.md"),
        "--output",
        str(tmp_path / "policy-freeze-v4.json"),
        "--dev-public",
        str(V4_DEV_PUBLIC),
        "--final-public",
        str(tmp_path / "natural-v4-fresh" / "public.json"),
        "--dev-run-id",
        "run-dev-policy-v4",
        "--final-run-id",
        "run-fresh-v4",
        "--proposer-id",
        "codex-gpt-5.6-sol",
        "--proposer-version",
        "2026-07-28-policy-v4",
        "--dev-dataset-id",
        "natural-identity-membership-dev-repair-v4",
        "--dev-case-count",
        "12",
        "--final-case-count",
        "6",
    )

    assert '"dev_dataset_id": "natural-identity-membership-dev-repair-v4"' in frozen.stdout
    assert '"dev_case_count": 12' in frozen.stdout
    assert '"final_case_count": 6' in frozen.stdout
