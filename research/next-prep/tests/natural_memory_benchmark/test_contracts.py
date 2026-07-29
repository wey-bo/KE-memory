from __future__ import annotations

import json

import pytest

from tools.natural_memory_benchmark.io import canonical_json_bytes, write_json_immutable
from tools.natural_memory_benchmark.models import NaturalBenchmarkCandidate


def test_write_json_immutable_allows_exact_replay(tmp_path):
    path = tmp_path / "artifact.json"
    value = {"schema_version": "test-v1", "items": [{"id": "A"}]}

    write_json_immutable(path, value)
    first_bytes = path.read_bytes()
    write_json_immutable(path, value)

    assert path.read_bytes() == first_bytes
    assert first_bytes == canonical_json_bytes(value)
    assert json.loads(first_bytes.decode("utf-8")) == value


def test_write_json_immutable_rejects_different_content(tmp_path):
    path = tmp_path / "artifact.json"
    write_json_immutable(path, {"schema_version": "test-v1", "items": []})

    with pytest.raises(FileExistsError):
        write_json_immutable(path, {"schema_version": "test-v1", "items": ["changed"]})


def test_candidate_public_view_excludes_gold_fields():
    candidate = NaturalBenchmarkCandidate(
        benchmark="locomo",
        item_id="LOCOMO-demo-Q001",
        source_id="locomo10",
        source_index=0,
        source_ref="sample_id=demo;qa_index=1",
        question="What did Caroline research?",
        slice_group="1",
        answer="Adoption agencies",
        answer_policy="gold",
        evidence_refs=["D1:3"],
        metadata={"category": 1, "rubric": ["gold-only"]},
    )

    public = candidate.public_item()
    gold = candidate.gold_item()

    assert public["item_id"] == candidate.item_id
    assert public["question"] == candidate.question
    assert "answer" not in public
    assert "evidence_refs" not in public
    assert "rubric" not in json.dumps(public, ensure_ascii=False)
    assert gold["answer"] == "Adoption agencies"
    assert gold["evidence_refs"] == ["D1:3"]
