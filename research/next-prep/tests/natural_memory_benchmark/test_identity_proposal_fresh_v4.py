from __future__ import annotations

import importlib
import json
import shutil
from pathlib import Path

import pytest

from tools.natural_memory_benchmark.io import canonical_json_bytes, load_json


V2_SOURCE = Path(
    "artifacts/identity-memory-experiment/natural-v2/source-cases.json"
)
V3_HIDDEN_SOURCE = Path(
    "artifacts/identity-memory-experiment/natural-v3-fresh/hidden-source-cases.json"
)
V4_HIDDEN_SOURCE = Path(
    "artifacts/identity-memory-experiment/natural-v4-fresh/hidden-source-cases.json"
)
POLICY_FREEZE = Path(
    "artifacts/identity-memory-experiment/dev-repair-v4/policy-freeze-v4.1-claude.json"
)
PASSING_DEV_RUN = Path(
    "artifacts/identity-memory-experiment/dev-repair-v4/model-runs/"
    "run-20260728T013000Z-claude-sonnet-4-6-dev-policy-v4-1"
)
WORKSPACE_ROOT = Path(".")
GENERATED_FILES = (
    "hidden-gold-evidence.json",
    "source-cases.json",
    "opaque-id-map.json",
    "chronology-receipt-v4.json",
    "preregistration.json",
    "public.json",
    "authority.json",
    "gold.json",
    "manifest.json",
)


def _module():
    try:
        return importlib.import_module(
            "tools.natural_memory_benchmark.identity_proposal_fresh_v4"
        )
    except ModuleNotFoundError as exc:
        pytest.fail(f"fresh v4 identity module missing: {exc}")


def _replace_json(path: Path, payload: object) -> None:
    if path.exists():
        path.chmod(0o644)
    path.write_bytes(canonical_json_bytes(payload))


def test_prepare_fresh_v4_is_hidden_only_balanced_fresh_and_deterministic(tmp_path):
    module = _module()
    root = tmp_path / "natural-v4-fresh"
    first = module.prepare_fresh_identity_v4(
        V2_SOURCE,
        V3_HIDDEN_SOURCE,
        V4_HIDDEN_SOURCE,
        root,
        policy_freeze_path=POLICY_FREEZE,
        workspace_root=WORKSPACE_ROOT,
    )
    first_bytes = {name: (root / name).read_bytes() for name in GENERATED_FILES}
    second = module.prepare_fresh_identity_v4(
        V2_SOURCE,
        V3_HIDDEN_SOURCE,
        V4_HIDDEN_SOURCE,
        root,
        policy_freeze_path=POLICY_FREEZE,
        workspace_root=WORKSPACE_ROOT,
    )

    assert first == second
    assert first_bytes == {name: (root / name).read_bytes() for name in GENERATED_FILES}
    assert first["case_count"] == 6
    assert first["dev_count"] == 0
    assert first["hidden_count"] == 6
    assert first["hidden_action_distribution"] == {
        "merge": 1,
        "keep_distinct": 1,
        "abstain_identity": 1,
        "include": 1,
        "exclude": 1,
        "abstain_membership": 1,
    }
    assert first["cross_session_hidden_count"] >= 2
    assert first["prior_evidence_overlap_count"] == 0
    assert first["prior_id_overlap_count"] == 0
    assert first["policy_chronology_valid"] is True
    public = load_json(root / "public.json")
    assert all(case["split"] == "hidden" for case in public["cases"])
    assert all(case["case_id"].startswith("case-") for case in public["cases"])
    assert all(
        mention["mention_id"].startswith("mention-")
        for case in public["cases"]
        for mention in case["mentions"]
    )
    assert all((root / name).stat().st_mode & 0o777 == 0o444 for name in GENERATED_FILES)


def test_prepare_fresh_v4_rejects_prior_hidden_evidence_overlap(tmp_path):
    module = _module()
    source = load_json(V4_HIDDEN_SOURCE)
    prior = json.loads(json.dumps(load_json(V3_HIDDEN_SOURCE)["cases"][0]))
    source["cases"][0] = prior
    hidden_path = tmp_path / "hidden-overlap.json"
    _replace_json(hidden_path, source)
    hidden_path.chmod(0o444)

    with pytest.raises(ValueError, match="prior hidden evidence overlap"):
        module.prepare_fresh_identity_v4(
            V2_SOURCE,
            V3_HIDDEN_SOURCE,
            hidden_path,
            tmp_path / "overlap",
            policy_freeze_path=POLICY_FREEZE,
            workspace_root=WORKSPACE_ROOT,
        )


def test_prepare_fresh_v4_rejects_hidden_source_with_unexpected_bytes(tmp_path):
    """Ordering is no longer carried by mtime, so tamper detection is by content.

    Was: back-date the hidden source past the dev run's ``score.json`` and expect
    "passing dev run must predate hidden source". Git preserves no mtime, so a
    checkout assigns arbitrary values and that ordering could not be established --
    it was already unsatisfiable at the reorganization baseline. The chronology
    receipt now carries the ordering; what remains checkable at this entry point is
    that a hidden source whose bytes differ from the frozen binding is refused.
    """
    module = _module()
    hidden_path = tmp_path / "hidden-source-cases.json"
    shutil.copyfile(V4_HIDDEN_SOURCE, hidden_path)
    original = hidden_path.read_bytes()
    mutated = original.replace(b'"dataset_id"', b'"dataset_Id"', 1)
    assert len(mutated) == len(original) and mutated != original, (
        "the mutation must actually change a byte, or this test proves nothing"
    )
    hidden_path.write_bytes(mutated)
    hidden_path.chmod(0o444)

    with pytest.raises(ValueError):
        module.prepare_fresh_identity_v4(
            V2_SOURCE,
            V3_HIDDEN_SOURCE,
            hidden_path,
            tmp_path / "mutated-hidden",
            policy_freeze_path=POLICY_FREEZE,
            workspace_root=WORKSPACE_ROOT,
        )


def test_formal_fresh_v4_requires_exact_inputs_and_read_only_outputs(tmp_path):
    module = _module()
    formal_root = Path("artifacts/identity-memory-experiment/natural-v4-fresh")
    module.prepare_fresh_identity_v4(
        V2_SOURCE,
        V3_HIDDEN_SOURCE,
        V4_HIDDEN_SOURCE,
        formal_root,
        policy_freeze_path=POLICY_FREEZE,
        workspace_root=WORKSPACE_ROOT,
    )
    copied_hidden = tmp_path / "hidden-source-cases.json"
    shutil.copyfile(V4_HIDDEN_SOURCE, copied_hidden)
    copied_hidden.chmod(0o444)
    with pytest.raises(ValueError, match="exact formal input paths"):
        module.validate_fresh_identity_v4(
            V2_SOURCE,
            V3_HIDDEN_SOURCE,
            copied_hidden,
            formal_root,
            policy_freeze_path=POLICY_FREEZE,
            workspace_root=WORKSPACE_ROOT,
        )

    # The second half previously chmod-ed the *committed* public.json to 0644 and
    # expected "must be read-only". Two problems: git preserves no write bit, so that
    # precondition cannot hold after a clone, and mutating tracked evidence to test a
    # guard damages the evidence. Content rejection is exercised on a copy instead.
    copied_root = tmp_path / "natural-v4-fresh"
    shutil.copytree(WORKSPACE_ROOT / formal_root, copied_root)
    target = copied_root / "public.json"
    target.chmod(0o644)
    original = target.read_bytes()
    mutated = original.replace(b'"case_count"', b'"case_Count"', 1)
    assert len(mutated) == len(original) and mutated != original, (
        "the mutation must actually change a byte, or this test proves nothing"
    )
    target.write_bytes(mutated)

    with pytest.raises(ValueError):
        module.validate_fresh_identity_v4(
            V2_SOURCE,
            V3_HIDDEN_SOURCE,
            V4_HIDDEN_SOURCE,
            copied_root,
            policy_freeze_path=POLICY_FREEZE,
            workspace_root=WORKSPACE_ROOT,
        )
