from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from tools.natural_memory_benchmark.identity_model_run import (
    freeze_identity_model_proposals,
    write_identity_model_dispatch,
)
from tools.natural_memory_benchmark.identity_proposal_opaque import (
    prepare_opaque_identity_slice,
)
from tools.natural_memory_benchmark.io import load_json, sha256_file


V1_SOURCE = Path(
    "artifacts/identity-memory-experiment/natural-v1/source-cases.json"
)
WORKSPACE_ROOT = Path(".")
ISOLATION_CONTEXT = "fresh-agent-no-history-declarative"


def _prepare(tmp_path: Path) -> tuple[Path, Path]:
    root = tmp_path / "natural-v2"
    prepare_opaque_identity_slice(V1_SOURCE, root, workspace_root=WORKSPACE_ROOT)
    prompt = tmp_path / "proposer-prompt.md"
    prompt.write_text("Read public.json and emit proposal JSON.\n", encoding="utf-8")
    prompt.chmod(0o444)
    return root, prompt


def _write_staged_proposals(tmp_path: Path, public_path: Path) -> Path:
    public = load_json(public_path)
    payload = {
        "schema_version": "natural-identity-proposals-v1",
        "dataset_id": public["dataset_id"],
        "run_id": "run-test-opaque-v2",
        "proposer_id": "test-model",
        "proposer_version": "1",
        "case_count": public["case_count"],
        "proposals": [
            {
                "case_id": case["case_id"],
                "relation_kind": case["relation_kind"],
                "action": "abstain",
                "confidence": 0.5,
                "evidence_mention_ids": [item["mention_id"] for item in case["mentions"]],
                "reason_code": "insufficient_public_evidence",
                "proposer_id": "test-model",
                "proposer_version": "1",
                "run_id": "run-test-opaque-v2",
            }
            for case in public["cases"]
        ],
    }
    staged = tmp_path / "staged-proposals.json"
    staged.write_text(json.dumps(payload), encoding="utf-8")
    return staged


def _write_dispatch(root: Path, prompt: Path, output: Path) -> dict:
    return write_identity_model_dispatch(
        root / "public.json",
        prompt,
        output,
        run_id="run-test-opaque-v2",
        proposer_id="test-model",
        proposer_version="1",
        isolation_context=ISOLATION_CONTEXT,
    )


def _run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "tools.natural_memory_benchmark.cli", *args],
        check=True,
        capture_output=True,
        text=True,
    )


def test_dispatch_and_freeze_validate_public_only_contract(tmp_path):
    root, prompt = _prepare(tmp_path)
    public_path = root / "public.json"
    dispatch_path = tmp_path / "dispatch.json"
    dispatch = _write_dispatch(root, prompt, dispatch_path)

    assert dispatch["allowed_input_sha256"] == {
        "proposer-prompt.md": sha256_file(prompt),
        "public.json": sha256_file(public_path),
    }
    assert dispatch["history_context_inherited"] is False
    assert dispatch["authority_or_gold_allowed"] is False
    assert dispatch_path.stat().st_mode & 0o777 == 0o444

    staged = _write_staged_proposals(tmp_path, public_path)
    output_path = tmp_path / "proposals.json"
    provenance_path = tmp_path / "provenance.json"
    first = freeze_identity_model_proposals(
        public_path,
        staged,
        output_path,
        provenance_path,
        prompt_path=prompt,
        dispatch_path=dispatch_path,
        isolation_context=ISOLATION_CONTEXT,
    )
    second = freeze_identity_model_proposals(
        public_path,
        staged,
        output_path,
        provenance_path,
        prompt_path=prompt,
        dispatch_path=dispatch_path,
        isolation_context=ISOLATION_CONTEXT,
    )

    assert first == second
    assert first["case_count"] == 12
    assert first["authority_or_gold_read_before_freeze"] is False
    assert first["allowed_input_sha256"] == dispatch["allowed_input_sha256"]
    assert first["dispatch_sha256"] == sha256_file(dispatch_path)
    assert first["proposals_sha256"] == sha256_file(output_path)
    assert output_path.stat().st_mode & 0o777 == 0o444
    assert provenance_path.stat().st_mode & 0o777 == 0o444


def test_dispatch_binds_the_prompt_and_freeze_detects_hash_changes(tmp_path):
    """Changing the prompt after dispatch must be caught by its hash.

    The first half of this test previously required the prompt to be mode 0444
    before dispatch would accept it. That precondition cannot hold on a fresh
    clone, and it was never the real protection: the binding that matters is the
    prompt hash recorded in the dispatch, which is what the second half asserts.
    """
    root = tmp_path / "natural-v2"
    prepare_opaque_identity_slice(V1_SOURCE, root, workspace_root=WORKSPACE_ROOT)
    prompt = tmp_path / "prompt.md"
    prompt.write_text("not frozen\n", encoding="utf-8")

    # A writable prompt is accepted -- that is the state after any checkout.
    dispatch_path = tmp_path / "dispatch.json"
    _write_dispatch(root, prompt, dispatch_path)
    staged = _write_staged_proposals(tmp_path, root / "public.json")

    # Changing it afterwards is not, because the dispatch bound its hash.
    prompt.write_text("changed after dispatch\n", encoding="utf-8")
    with pytest.raises(ValueError, match="prompt hash mismatch"):
        freeze_identity_model_proposals(
            root / "public.json",
            staged,
            tmp_path / "proposals.json",
            tmp_path / "provenance.json",
            prompt_path=prompt,
            dispatch_path=dispatch_path,
            isolation_context=ISOLATION_CONTEXT,
        )


def test_freeze_accepts_an_unchanged_prompt_at_clone_mode(tmp_path):
    """The inverse: right bytes at 0644 must not be rejected."""
    root = tmp_path / "natural-v2"
    prepare_opaque_identity_slice(V1_SOURCE, root, workspace_root=WORKSPACE_ROOT)
    prompt = tmp_path / "prompt.md"
    prompt.write_text("stable prompt\n", encoding="utf-8")
    prompt.chmod(0o644)

    dispatch_path = tmp_path / "dispatch.json"
    _write_dispatch(root, prompt, dispatch_path)
    staged = _write_staged_proposals(tmp_path, root / "public.json")

    assert prompt.stat().st_mode & 0o222, "precondition: writable, as after a clone"
    freeze_identity_model_proposals(
        root / "public.json",
        staged,
        tmp_path / "proposals.json",
        tmp_path / "provenance.json",
        prompt_path=prompt,
        dispatch_path=dispatch_path,
        isolation_context=ISOLATION_CONTEXT,
    )


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("unknown_evidence", "unknown evidence mention id"),
        ("missing_case", "proposal case coverage mismatch"),
        ("wrong_relation", "proposal relation kind mismatch"),
    ],
)
def test_freeze_rejects_invalid_public_contract(tmp_path, mutation, message):
    root, prompt = _prepare(tmp_path)
    dispatch_path = tmp_path / "dispatch.json"
    _write_dispatch(root, prompt, dispatch_path)
    staged = _write_staged_proposals(tmp_path, root / "public.json")
    payload = load_json(staged)
    if mutation == "unknown_evidence":
        payload["proposals"][0]["evidence_mention_ids"] = [
            "mention-deadbeefdeadbeef"
        ]
    elif mutation == "missing_case":
        payload["proposals"][-1]["case_id"] = "case-0000000000000000"
    else:
        payload["proposals"][0]["relation_kind"] = "membership"
    staged.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match=message):
        freeze_identity_model_proposals(
            root / "public.json",
            staged,
            tmp_path / "proposals.json",
            tmp_path / "provenance.json",
            prompt_path=prompt,
            dispatch_path=dispatch_path,
            isolation_context=ISOLATION_CONTEXT,
        )


def test_cli_prepares_validates_dispatches_and_freezes(tmp_path):
    root = tmp_path / "natural-v2"
    prepare = _run_cli(
        "prepare-natural-identity-opaque-slice",
        "--v1-source",
        str(V1_SOURCE),
        "--output-root",
        str(root),
        "--workspace-root",
        ".",
    )
    assert '"identifier_policy_valid": true' in prepare.stdout
    validate = _run_cli(
        "validate-natural-identity-opaque-slice",
        "--v1-source",
        str(V1_SOURCE),
        "--root",
        str(root),
        "--workspace-root",
        ".",
    )
    assert '"semantic_equivalence_valid": true' in validate.stdout

    prompt = tmp_path / "prompt.md"
    prompt.write_text("Read public.json and emit proposal JSON.\n", encoding="utf-8")
    prompt.chmod(0o444)
    dispatch_path = tmp_path / "dispatch.json"
    dispatch = _run_cli(
        "prepare-identity-model-dispatch",
        "--public",
        str(root / "public.json"),
        "--prompt",
        str(prompt),
        "--output",
        str(dispatch_path),
        "--run-id",
        "run-test-opaque-v2",
        "--proposer-id",
        "test-model",
        "--proposer-version",
        "1",
        "--isolation-context",
        ISOLATION_CONTEXT,
    )
    assert '"status": "frozen"' in dispatch.stdout

    staged = _write_staged_proposals(tmp_path, root / "public.json")
    frozen = _run_cli(
        "freeze-identity-model-proposals",
        "--public",
        str(root / "public.json"),
        "--staged-proposals",
        str(staged),
        "--output",
        str(tmp_path / "proposals.json"),
        "--provenance",
        str(tmp_path / "provenance.json"),
        "--prompt",
        str(prompt),
        "--dispatch",
        str(dispatch_path),
        "--isolation-context",
        ISOLATION_CONTEXT,
    )
    assert '"case_count": 12' in frozen.stdout
