from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from knowledge_pipeline.cli import build_parser
from knowledge_pipeline.keywords import (
    prepare_keyword_payloads,
    validate_keyword_batch,
    validate_keyword_output,
)


PROMPT = """# Knowledge Keyword Extraction

## Input Boundary
Only supplied knowledge.
## Output Contract
JSON only.
## Completeness Checklist
Cover meaningful terms.
## Evidence Rules
Use supplied fields.
## Epistemic Rules
Keywords are retrieval aids.
## Forbidden Behavior
No vocabulary IDs.
## Final Self-Check
Validate coverage.
"""


def _record(knowledge_id: str, candidate_id: str, status: str, statement: str) -> dict[str, object]:
    return {
        "knowledge": {
            "knowledge_id": knowledge_id,
            "candidate_id": candidate_id,
            "statement": statement,
            "subject": "用户",
            "predicate": "学习",
            "object": "Python",
            "qualifiers": {
                "modality": "planned",
                "polarity": "positive",
                "temporal": ["明天"],
                "conditions": [],
                "scope": [],
            },
            "source_status": "user_reported",
            "derivation": "explicit",
            "evidence": [{"quote": statement}],
            "confidence": 0.9,
        },
        "projection": {"status": status, "source_turn": 0, "stage": "turn"},
    }


def _final_fixture(tmp_path: Path) -> Path:
    path = tmp_path / "final-knowledge.json"
    value = {
        "schema_version": "final-knowledge-v1",
        "active_ids": ["K_A_001", "K_B_001"],
        "counts": {"active": 2, "corrected": 1},
        "records": [
            _record("K_A_001", "CAND-A", "active", "用户计划明天学习 Python。"),
            _record("K_A_OLD", "CAND-A", "corrected", "用户计划学习旧课程。"),
            _record("K_B_001", "CAND-B", "active", "用户正在学习 Python。"),
        ],
        "provenance": {"turn_manifest_sha256": "1" * 64, "dialogue_manifest_sha256": "2" * 64},
    }
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def _raw_for(payload: dict[str, object]) -> dict[str, object]:
    items = []
    prefix = str(payload["keyword_id_prefix"])
    index = 1
    for knowledge in payload["active_knowledge"]:
        keywords = [{
            "keyword_id": f"{prefix}{index:04d}",
            "knowledge_id": knowledge["knowledge_id"],
            "surface": "Python",
            "normalized_zh": "Python",
            "query_lemma": "python",
            "keyword_kind": "lexical",
            "keyword_type": "concept",
            "semantic_role": "object",
            "source_field": "object",
            "part_of_speech": "noun",
            "sense_key": "python_programming_language",
            "sense_hint": "the Python programming language",
            "lookup_targets": ["wordnet", "schema_org"],
            "normalized_value": None,
            "datatype": None,
            "unit": None,
            "translation_confidence": 1.0,
        }]
        index += 1
        qualifiers = knowledge["qualifiers"]
        for temporal in qualifiers["temporal"]:
            keywords.append({
                "keyword_id": f"{prefix}{index:04d}",
                "knowledge_id": knowledge["knowledge_id"],
                "surface": temporal,
                "normalized_zh": temporal,
                "query_lemma": "time",
                "keyword_kind": "literal",
                "keyword_type": "time",
                "semantic_role": "time",
                "source_field": "qualifiers.temporal",
                "part_of_speech": "none",
                "sense_key": None,
                "sense_hint": "time qualifier",
                "lookup_targets": ["exact"],
                "normalized_value": temporal,
                "datatype": "time",
                "unit": None,
                "translation_confidence": 1.0,
            })
            index += 1
        modality = qualifiers["modality"]
        keywords.append({
            "keyword_id": f"{prefix}{index:04d}",
            "knowledge_id": knowledge["knowledge_id"],
            "surface": modality,
            "normalized_zh": modality,
            "query_lemma": modality,
            "keyword_kind": "qualifier",
            "keyword_type": "modality",
            "semantic_role": "modality",
            "source_field": "qualifiers.modality",
            "part_of_speech": "none",
            "sense_key": None,
            "sense_hint": "knowledge modality",
            "lookup_targets": ["exact"],
            "normalized_value": modality,
            "datatype": "modality",
            "unit": None,
            "translation_confidence": 1.0,
        })
        index += 1
        items.append({
            "knowledge_id": knowledge["knowledge_id"],
            "keywords": keywords,
            "no_keyword_reason": None,
        })
    return {"candidate_id": payload["candidate_id"], "items": items}


def test_prepare_keyword_payloads_contains_active_knowledge_only(tmp_path: Path) -> None:
    final_path = _final_fixture(tmp_path)
    prompt = tmp_path / "prompt.md"
    prompt.write_text(PROMPT, encoding="utf-8")
    manifest_path = prepare_keyword_payloads(final_path, tmp_path / "prepared", prompt)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert len(manifest["candidates"]) == 2
    payloads = [json.loads((manifest_path.parent / item["payload_file"]).read_text(encoding="utf-8")) for item in manifest["candidates"]]
    assert {knowledge["knowledge_id"] for payload in payloads for knowledge in payload["active_knowledge"]} == {"K_A_001", "K_B_001"}
    assert all("K_A_OLD" not in json.dumps(payload) for payload in payloads)


def test_validate_keyword_output_requires_exact_active_coverage(tmp_path: Path) -> None:
    final_path = _final_fixture(tmp_path)
    prompt = tmp_path / "prompt.md"
    prompt.write_text(PROMPT, encoding="utf-8")
    manifest = prepare_keyword_payloads(final_path, tmp_path / "prepared", prompt)
    entry = json.loads(manifest.read_text(encoding="utf-8"))["candidates"][0]
    payload = json.loads((manifest.parent / entry["payload_file"]).read_text(encoding="utf-8"))
    raw = _raw_for(payload)
    raw["items"] = []

    with pytest.raises(ValueError, match="coverage"):
        validate_keyword_output(raw, payload)


def test_validate_keyword_output_rejects_vocabulary_id_and_untraceable_surface(tmp_path: Path) -> None:
    final_path = _final_fixture(tmp_path)
    prompt = tmp_path / "prompt.md"
    prompt.write_text(PROMPT, encoding="utf-8")
    manifest = prepare_keyword_payloads(final_path, tmp_path / "prepared", prompt)
    entry = json.loads(manifest.read_text(encoding="utf-8"))["candidates"][0]
    payload = json.loads((manifest.parent / entry["payload_file"]).read_text(encoding="utf-8"))
    raw = _raw_for(payload)
    raw["items"][0]["keywords"][0]["id"] = "https://schema.org/Thing"
    with pytest.raises(ValueError, match="KeywordPassOutput"):
        validate_keyword_output(raw, payload)

    raw = _raw_for(payload)
    raw["items"][0]["keywords"][0]["surface"] = "Java"
    with pytest.raises(ValueError, match="source_field"):
        validate_keyword_output(raw, payload)


def test_validate_keyword_output_requires_contiguous_candidate_keyword_ids(tmp_path: Path) -> None:
    final_path = _final_fixture(tmp_path)
    prompt = tmp_path / "prompt.md"
    prompt.write_text(PROMPT, encoding="utf-8")
    manifest = prepare_keyword_payloads(final_path, tmp_path / "prepared", prompt)
    entry = json.loads(manifest.read_text(encoding="utf-8"))["candidates"][0]
    payload = json.loads((manifest.parent / entry["payload_file"]).read_text(encoding="utf-8"))
    raw = _raw_for(payload)
    raw["items"][0]["keywords"][0]["keyword_id"] = str(payload["keyword_id_prefix"]) + "0004"

    with pytest.raises(ValueError, match="contiguous"):
        validate_keyword_output(raw, payload)


def test_validate_keyword_output_rejects_permuted_contiguous_ids(tmp_path: Path) -> None:
    final_path = _final_fixture(tmp_path)
    prompt = tmp_path / "prompt.md"
    prompt.write_text(PROMPT, encoding="utf-8")
    manifest = prepare_keyword_payloads(final_path, tmp_path / "prepared", prompt)
    entry = json.loads(manifest.read_text(encoding="utf-8"))["candidates"][0]
    payload = json.loads((manifest.parent / entry["payload_file"]).read_text(encoding="utf-8"))
    raw = _raw_for(payload)
    first = raw["items"][0]["keywords"][0]
    second = raw["items"][0]["keywords"][1]
    prefix = str(payload["keyword_id_prefix"])
    first["keyword_id"] = prefix + "0002"
    second["keyword_id"] = prefix + "0001"

    with pytest.raises(ValueError, match="canonical order"):
        validate_keyword_output(raw, payload)


def test_validate_keyword_batch_is_complete_and_raw_immutable(tmp_path: Path) -> None:
    final_path = _final_fixture(tmp_path)
    prompt = tmp_path / "prompt.md"
    prompt.write_text(PROMPT, encoding="utf-8")
    manifest_path = prepare_keyword_payloads(final_path, tmp_path / "prepared", prompt)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    before: dict[str, str] = {}
    for entry in manifest["candidates"]:
        payload = json.loads((manifest_path.parent / entry["payload_file"]).read_text(encoding="utf-8"))
        raw_file = raw_dir / entry["canonical_filename"]
        raw_file.write_text(json.dumps(_raw_for(payload), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        before[raw_file.name] = hashlib.sha256(raw_file.read_bytes()).hexdigest()

    output = tmp_path / "keyword-pass.json"
    validate_keyword_batch(manifest_path, raw_dir, output)
    aggregate = json.loads(output.read_text(encoding="utf-8"))

    assert len(aggregate["candidates"]) == 2
    assert aggregate["schema_version"] == "keyword-pass-v2"
    assert aggregate["canonical_keywords"]
    assert all(hashlib.sha256((raw_dir / name).read_bytes()).hexdigest() == digest for name, digest in before.items())


def test_cli_registers_keyword_commands() -> None:
    prepare = build_parser().parse_args(["prepare-keywords"])
    validate = build_parser().parse_args(["validate-keywords"])

    assert prepare.final_knowledge == Path("knowledge-extraction/final-knowledge.json")
    assert validate.raw_dir == Path("knowledge-extraction/keyword-pass/raw")
