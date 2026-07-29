from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from tools.amr_pilot.gold import load_and_validate_gold, validate_gold_approval
from tools.amr_pilot.inputs import PilotInputs
from tools.amr_pilot.models import SentenceSample, SourceRecord


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def pilot_inputs() -> PilotInputs:
    samples: list[SentenceSample] = []
    records: list[SourceRecord] = []
    phenomena = (
        "event_roles",
        "time_quantity_condition",
        "negation_modality_intent",
        "causality_comparison_multiclause",
    )
    for index in range(12):
        number = index + 1
        text = f"Person {number} completed task {number}."
        source = {
            "dataset": "Synthetic",
            "source_url": "https://example.test/source",
            "source_revision": "fixture-revision",
            "source_artifact_sha256": "4" * 64,
            "record_locator": f"record={number}",
            "message_locator": f"message={number}",
            "speaker": "user",
        }
        records.append(
            SourceRecord.model_validate(
                {
                    "source_record_id": f"SRC-{number:03d}",
                    "candidate_id": f"CAND-{index}",
                    "text": text,
                    "text_sha256": sha256(text),
                    "source": source,
                }
            )
        )
        samples.append(
            SentenceSample.model_validate(
                {
                    "sample_id": f"AMR-S{number:03d}",
                    "candidate_id": f"CAND-{index}",
                    "text": text,
                    "language": "en",
                    "phenomenon": phenomena[index // 3],
                    "text_sha256": sha256(text),
                    "source_record_id": f"SRC-{number:03d}",
                    "sentence_occurrence_index": 0,
                    "source": source,
                }
            )
        )
    return PilotInputs(tuple(samples), tuple(records))


def write_gold(path: Path, inputs: PilotInputs) -> None:
    checklists = []
    for sample in inputs.samples:
        checklists.append(
            {
                "sample_id": sample.sample_id,
                "source_text_sha256": sample.text_sha256,
                "items": [
                    {
                        "item_id": f"{sample.sample_id}-G001",
                        "statement": "The person completed the task.",
                        "importance": "critical",
                        "weight": 2,
                        "evidence_quotes": ["completed"],
                        "category": "event",
                    }
                ],
                "forbidden_inferences": ["The task failed."],
            }
        )
    path.write_text(
        json.dumps(
            {
                "schema_version": "amr-pilot-gold-draft-v1",
                "status": "draft",
                "checklists": checklists,
            }
        ),
        encoding="utf-8",
    )


def test_gold_requires_complete_source_bound_checklists(tmp_path: Path) -> None:
    inputs = pilot_inputs()
    draft = tmp_path / "gold.json"
    write_gold(draft, inputs)

    result = load_and_validate_gold(draft, inputs)

    assert len(result.checklists) == 12
    assert result.checklists[0].items[0].weight == 2


def test_gold_rejects_evidence_absent_from_sentence(tmp_path: Path) -> None:
    inputs = pilot_inputs()
    draft = tmp_path / "gold.json"
    write_gold(draft, inputs)
    document = json.loads(draft.read_text(encoding="utf-8"))
    document["checklists"][0]["items"][0]["evidence_quotes"] = ["missing quote"]
    draft.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(ValueError, match="evidence quote"):
        load_and_validate_gold(draft, inputs)


def test_gold_rejects_missing_sample_checklist(tmp_path: Path) -> None:
    inputs = pilot_inputs()
    draft = tmp_path / "gold.json"
    write_gold(draft, inputs)
    document = json.loads(draft.read_text(encoding="utf-8"))
    document["checklists"].pop()
    draft.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(ValueError, match="exactly cover"):
        load_and_validate_gold(draft, inputs)


def test_gold_approval_must_bind_exact_draft_hash(tmp_path: Path) -> None:
    inputs = pilot_inputs()
    draft = tmp_path / "gold.json"
    write_gold(draft, inputs)
    approval = tmp_path / "approval.json"
    approval.write_text(
        json.dumps(
            {
                "schema_version": "amr-pilot-gold-approval-v1",
                "status": "approved",
                "gold_sha256": hashlib.sha256(draft.read_bytes()).hexdigest(),
                "approved_by": "user",
                "approved_at": "2026-07-24T12:00:00Z",
            }
        ),
        encoding="utf-8",
    )

    validated = validate_gold_approval(draft, approval, inputs)
    assert validated.approved_by == "user"

    draft.write_text(draft.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="gold_sha256"):
        validate_gold_approval(draft, approval, inputs)
