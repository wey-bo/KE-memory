"""Validate the independent semantic gold and its explicit user approval."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from tools.amr_pilot.inputs import PilotInputs
from tools.amr_pilot.models import GoldApproval, GoldDraft


def _read_json(path: str | Path) -> object:
    source_path = Path(path)
    try:
        return json.loads(source_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"could not parse {source_path}: {error}") from error


def load_and_validate_gold(path: str | Path, inputs: PilotInputs) -> GoldDraft:
    draft = GoldDraft.model_validate(_read_json(path))
    expected_ids = [sample.sample_id for sample in inputs.samples]
    actual_ids = [checklist.sample_id for checklist in draft.checklists]
    if actual_ids != expected_ids:
        raise ValueError("gold checklists must exactly cover the ordered input samples")

    samples = {sample.sample_id: sample for sample in inputs.samples}
    global_item_ids: set[str] = set()
    for checklist in draft.checklists:
        sample = samples[checklist.sample_id]
        if checklist.source_text_sha256 != sample.text_sha256:
            raise ValueError(f"gold source_text_sha256 mismatch for {sample.sample_id}")
        for item in checklist.items:
            if item.item_id in global_item_ids:
                raise ValueError(f"duplicate gold item ID: {item.item_id}")
            global_item_ids.add(item.item_id)
            for quote in item.evidence_quotes:
                if quote not in sample.text:
                    raise ValueError(f"gold evidence quote is absent from {sample.sample_id}: {quote}")
    return draft


def validate_gold_approval(
    draft_path: str | Path,
    approval_path: str | Path,
    inputs: PilotInputs,
) -> GoldApproval:
    load_and_validate_gold(draft_path, inputs)
    approval = GoldApproval.model_validate(_read_json(approval_path))
    actual_hash = hashlib.sha256(Path(draft_path).read_bytes()).hexdigest()
    if approval.gold_sha256 != actual_hash:
        raise ValueError("approval gold_sha256 does not match the exact draft file")
    return approval
