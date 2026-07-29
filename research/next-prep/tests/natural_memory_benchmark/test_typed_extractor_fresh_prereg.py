from __future__ import annotations

from pathlib import Path

import pytest

from tools.natural_memory_benchmark.cli import main as cli_main
from tools.natural_memory_benchmark.io import load_json, sha256_file
from tools.natural_memory_benchmark.typed_extractor_fresh_prereg import (
    freeze_typed_extractor_fresh_preregistration,
    validate_typed_extractor_fresh_preregistration,
)


BRIDGE = Path(
    "artifacts/automatic-extraction-assessment/bridge-v3/compatibility-ledger.json"
)
L1_PROMPT = Path(
    "artifacts/automatic-extraction-assessment/typed-extractor-v2-l1-dev-policies/"
    "prompt-v6/proposer-prompt-l1.md"
)
L2_PROMPT = Path(
    "artifacts/automatic-extraction-assessment/typed-extractor-v2-l2-dev-v9/"
    "proposer-prompt-l2.md"
)
L1_ROOT = Path(
    "artifacts/automatic-extraction-assessment/typed-extractor-v2-dev-v3"
)
L2_ROOT = Path(
    "artifacts/automatic-extraction-assessment/typed-extractor-v2-l2-dev-v9"
)
FREEZE_TIME = "2026-07-28T09:30:00Z"


def _freeze(tmp_path: Path):
    return freeze_typed_extractor_fresh_preregistration(
        output_root=tmp_path / "prereg",
        evaluation_root=tmp_path / "fresh-hidden",
        workspace_root=Path("."),
        bridge_ledger_path=BRIDGE,
        l1_prompt_path=L1_PROMPT,
        l2_prompt_path=L2_PROMPT,
        l1_dev_root=L1_ROOT,
        l2_dev_root=L2_ROOT,
        freeze_time=FREEZE_TIME,
    )


def test_freeze_preregistration_binds_protocol_inputs_and_zero_write_boundary(
    tmp_path: Path,
) -> None:
    result = _freeze(tmp_path)
    path = tmp_path / "prereg" / "preregistration.json"
    payload = load_json(path)

    assert result == payload
    assert payload["schema_version"] == "typed-extractor-fresh-preregistration-v1"
    assert payload["selection"]["l1_case_count"] == 24
    assert payload["selection"]["l2_case_count"] == 8
    assert payload["selection"]["l1_namespace"] == (
        "typed-extractor-l1-fresh-hidden-v1:2026-07-28"
    )
    assert payload["selection"]["l2_namespace"] == (
        "typed-extractor-l2-fresh-hidden-v1:2026-07-28"
    )
    assert payload["model_policy"]["requested_model"] == "deepseek-chat"
    assert payload["model_policy"]["semantic_retry_allowed"] is False
    assert payload["chronology"]["hidden_artifacts_absent_at_freeze"] is True
    assert payload["chronology"]["trusted_timestamp_authority"] is False
    assert payload["input_sha256"]["bridge-v3/compatibility-ledger.json"] == (
        sha256_file(BRIDGE)
    )
    assert payload["input_sha256"]["l1/proposer-prompt-l1.md"] == (
        sha256_file(L1_PROMPT)
    )
    assert payload["input_sha256"]["l2/proposer-prompt-l2.md"] == (
        sha256_file(L2_PROMPT)
    )
    assert set(payload["claim_boundary"].values()) <= {False, 0, "structured_l2_identity_unresolved"}
    assert payload["claim_boundary"]["automatic_l1_write_count"] == 0
    assert payload["claim_boundary"]["automatic_l2_write_count"] == 0
    assert path.stat().st_mode & 0o777 == 0o444
    assert not (tmp_path / "fresh-hidden").exists()


def test_validate_preregistration_rehashes_every_bound_input(tmp_path: Path) -> None:
    _freeze(tmp_path)
    result = validate_typed_extractor_fresh_preregistration(
        root=tmp_path / "prereg",
        evaluation_root=tmp_path / "fresh-hidden",
        workspace_root=Path("."),
        bridge_ledger_path=BRIDGE,
        l1_prompt_path=L1_PROMPT,
        l2_prompt_path=L2_PROMPT,
        l1_dev_root=L1_ROOT,
        l2_dev_root=L2_ROOT,
        freeze_time=FREEZE_TIME,
    )

    assert result == {
        "status": "valid",
        "l1_case_count": 24,
        "l2_case_count": 8,
        "hidden_artifacts_absent": True,
    }


def test_freeze_rejects_hidden_artifacts_that_predate_preregistration(
    tmp_path: Path,
) -> None:
    (tmp_path / "fresh-hidden").mkdir()

    with pytest.raises(ValueError, match="must be absent before preregistration"):
        _freeze(tmp_path)


def test_cli_freezes_and_validates_preregistration(tmp_path: Path) -> None:
    prereg = tmp_path / "prereg"
    evaluation = tmp_path / "fresh-hidden"
    common = [
        "--evaluation-root", str(evaluation),
        "--workspace-root", ".",
        "--bridge-ledger", str(BRIDGE),
        "--l1-prompt", str(L1_PROMPT),
        "--l2-prompt", str(L2_PROMPT),
        "--l1-dev-root", str(L1_ROOT),
        "--l2-dev-root", str(L2_ROOT),
        "--freeze-time", FREEZE_TIME,
    ]

    assert cli_main([
        "freeze-typed-extractor-fresh-preregistration",
        *common,
        "--output-root", str(prereg),
    ]) == 0
    assert cli_main([
        "validate-typed-extractor-fresh-preregistration",
        *common,
        "--root", str(prereg),
    ]) == 0
