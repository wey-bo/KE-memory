from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

import knowledge_pipeline.turn_pass as turn_pass
from knowledge_pipeline.cli import main
from knowledge_pipeline.source import load_turn_units
from knowledge_pipeline.source_segments import ToolResultSpan
from knowledge_pipeline.turn_pass import (
    candidate_namespace,
    prepare_turn_payloads,
    validate_turn_batch,
    validate_turn_output,
)


DATASET = (
    Path(__file__).resolve().parents[2]
    / "data"
    / "gold-candidates"
    / "KE-test.json"
)
PROMPT = Path(__file__).resolve().parents[2] / "knowledge-extraction" / "prompts" / "turn_knowledge_extraction.md"
SEGMENTS = Path(__file__).resolve().parents[2] / "knowledge-extraction" / "source-segments.json"


def raw_output(
    candidate_id: str = "candidate-alpha",
    turn_index: int = 0,
    user: str = "I prefer tea. I prefer tea.",
    agent: str = "I can recommend tea.",
) -> dict[str, object]:
    namespace = candidate_namespace(candidate_id)
    return {
        "candidate_id": candidate_id,
        "turn_index": turn_index,
        "context_completions": [],
        "knowledge": [
            {
                "knowledge_id": f"K_{namespace}_{turn_index:03d}_001",
                "candidate_id": candidate_id,
                "statement": "The user prefers tea.",
                "subject": "user",
                "predicate": "prefers",
                "object": "tea",
                "qualifiers": {"modality": "preferred", "polarity": "positive"},
                "source_status": "user_reported",
                "derivation": "explicit",
                "evidence": [{"turn_index": turn_index, "message": "user", "occurrence_index": 0, "quote": "I prefer tea."}],
                "inference_basis": None,
                "confidence": 0.9,
            }
        ],
    }


def test_prepare_turn_payloads_writes_isolated_schema_backed_payloads(tmp_path: Path) -> None:
    manifest_path = prepare_turn_payloads(DATASET, tmp_path, PROMPT, SEGMENTS)
    payload_path = tmp_path / "knowledge-extraction" / "turn-pass" / "prepared" / "payloads" / "0000-0000.json"
    payload = json.loads(payload_path.read_text(encoding="utf-8"))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert len(list(payload_path.parent.glob("*.json"))) == 43
    assert set(payload) == {
        "prompt_version", "candidate_id", "turn_index", "source", "user", "agent",
        "source_coordinates", "output_contract", "candidate_namespace",
        "knowledge_id_prefix", "context_completion_id_prefix", "source_segments_sha256",
        "tool_result_spans",
    }
    assert set(payload["source_coordinates"]) == {"user", "agent"}
    assert "previous" not in json.dumps(payload, ensure_ascii=False).lower()
    assert "old output" not in json.dumps(payload, ensure_ascii=False).lower()
    assert payload["output_contract"] == __import__("knowledge_pipeline.models", fromlist=["TurnPassOutput"]).TurnPassOutput.model_json_schema()
    assert set(manifest) == {
        "prompt_version", "prompt_sha256", "prompt_file", "output_contract_sha256",
        "source_segments_file", "source_segments_sha256", "turns",
    }
    assert len(manifest["turns"]) == 43


def test_validate_turn_output_rejects_candidate_mismatch() -> None:
    with pytest.raises(ValueError, match="candidate_id"):
        validate_turn_output(raw_output(candidate_id="candidate-beta"), "candidate-alpha", 0, "I prefer tea. I prefer tea.", "I can recommend tea.")


@pytest.mark.parametrize("knowledge_id", ["K_candidate-alpha_0_1", "K_candidate-beta-ffffffffffff_000_001"])
def test_validate_turn_output_rejects_invalid_or_cross_candidate_knowledge_id(knowledge_id: str) -> None:
    output = raw_output()
    output["knowledge"][0]["knowledge_id"] = knowledge_id  # type: ignore[index]
    with pytest.raises(ValueError, match="knowledge_id"):
        validate_turn_output(output, "candidate-alpha", 0, "I prefer tea. I prefer tea.", "I can recommend tea.")


def test_validate_turn_output_rejects_duplicate_ids() -> None:
    output = raw_output()
    output["knowledge"].append(output["knowledge"][0].copy())  # type: ignore[index]
    with pytest.raises(ValueError, match="knowledge IDs"):
        validate_turn_output(output, "candidate-alpha", 0, "I prefer tea. I prefer tea.", "I can recommend tea.")


@pytest.mark.parametrize("quote, occurrence", [("missing", 0), ("I prefer tea.", 2)])
def test_validate_turn_output_rejects_unknown_or_missing_evidence_quote(quote: str, occurrence: int) -> None:
    output = raw_output()
    evidence = output["knowledge"][0]["evidence"][0]  # type: ignore[index]
    evidence["quote"] = quote
    evidence["occurrence_index"] = occurrence
    with pytest.raises(ValueError, match="quote occurrence"):
        validate_turn_output(output, "candidate-alpha", 0, "I prefer tea. I prefer tea.", "I can recommend tea.")


def test_validate_turn_output_materializes_repeated_occurrence_and_completion_evidence() -> None:
    output = raw_output()
    output["knowledge"][0]["evidence"][0]["occurrence_index"] = 1  # type: ignore[index]
    output["context_completions"] = [{
        "completion_id": f"C_{candidate_namespace('candidate-alpha')}_000_001",
        "candidate_id": "candidate-alpha",
        "turn_index": 0,
        "kind": "coreference",
        "original_span": "it",
        "interpretation": "tea",
        "evidence": [{"turn_index": 0, "message": "user", "occurrence_index": 1, "quote": "I prefer tea."}],
        "confidence": 0.8,
        "ambiguity": False,
    }]

    validated = validate_turn_output(output, "candidate-alpha", 0, "I prefer tea. I prefer tea.", "I can recommend tea.")

    assert validated["knowledge"][0]["evidence"][0]["start"] == 14
    assert validated["context_completions"][0]["evidence"][0]["candidate_id"] == "candidate-alpha"


def test_tool_observed_requires_explicit_tool_result_span() -> None:
    agent = "[工具调用] change() [工具结果] item was cancelled [工具调用] next()"
    output = raw_output(user="Please cancel it.", agent=agent)
    item = output["knowledge"][0]  # type: ignore[index]
    item.update({
        "knowledge_id": f"K_{candidate_namespace('candidate-alpha')}_000_001",
        "source_status": "tool_observed",
        "evidence": [{"turn_index": 0, "message": "agent", "occurrence_index": 0, "quote": "item was cancelled"}],
    })
    result_quote = "item was cancelled"
    start = agent.index(result_quote)
    spans = (ToolResultSpan(result_quote, 0, 0, start, start + len(result_quote)),)
    assert validate_turn_output(output, "candidate-alpha", 0, "Please cancel it.", agent, tool_result_spans=spans)["knowledge"][0]["evidence"][0]["evidence_role"] == "tool_observed"

    item["evidence"] = [{"turn_index": 0, "message": "agent", "occurrence_index": 0, "quote": "change()"}]
    with pytest.raises(ValueError, match="tool_observed"):
        validate_turn_output(output, "candidate-alpha", 0, "Please cancel it.", agent, tool_result_spans=spans)

    item["evidence"] = [{"turn_index": 0, "message": "agent", "occurrence_index": 0, "quote": "[工具结果]"}]
    with pytest.raises(ValueError, match="tool_observed"):
        validate_turn_output(output, "candidate-alpha", 0, "Please cancel it.", agent, tool_result_spans=spans)


def test_explicit_tool_result_span_does_not_extend_to_message_end() -> None:
    agent = "[工具结果] preference saved. I recommend tea."
    result_quote = "preference saved."
    start = agent.index(result_quote)
    spans = (ToolResultSpan(result_quote, 0, 0, start, start + len(result_quote)),)
    output = raw_output(user="save it", agent=agent)
    item = output["knowledge"][0]  # type: ignore[index]
    item.update(source_status="tool_observed", evidence=[{
        "turn_index": 0, "message": "agent", "occurrence_index": 0, "quote": result_quote,
    }])
    validate_turn_output(output, "candidate-alpha", 0, "save it", agent, tool_result_spans=spans)

    item["evidence"] = [{"turn_index": 0, "message": "agent", "occurrence_index": 0, "quote": "I recommend tea."}]
    with pytest.raises(ValueError, match="tool_observed"):
        validate_turn_output(output, "candidate-alpha", 0, "save it", agent, tool_result_spans=spans)
    item["source_status"] = "agent_generated"
    validate_turn_output(output, "candidate-alpha", 0, "save it", agent, tool_result_spans=spans)
    item["evidence"] = [{"turn_index": 0, "message": "agent", "occurrence_index": 0, "quote": result_quote}]
    with pytest.raises(ValueError, match="agent_generated"):
        validate_turn_output(output, "candidate-alpha", 0, "save it", agent, tool_result_spans=spans)


def test_prepare_turns_remains_compatible(tmp_path: Path) -> None:
    assert main(["prepare-turns", "--input", str(DATASET), "--output-dir", str(tmp_path)]) == 0
    assert (tmp_path / "knowledge-extraction" / "inputs" / "manifest.json").is_file()


def test_validate_turns_rejects_missing_and_extra_raw_outputs_atomically(tmp_path: Path) -> None:
    prepared = tmp_path / "prepared"
    manifest_path = prepare_turn_payloads(DATASET, prepared, PROMPT, SEGMENTS)
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    units = load_turn_units(DATASET)
    first = units[0]
    (raw_dir / "0000-0000.json").write_text(json.dumps(raw_output(first.candidate_id, first.turn_index, first.user, first.agent), ensure_ascii=False), encoding="utf-8")

    with pytest.raises(ValueError, match="missing raw output"):
        main(["validate-turns", "--manifest", str(manifest_path), "--raw-dir", str(raw_dir), "--output-dir", str(tmp_path / "published")])
    assert not (tmp_path / "published" / "knowledge-extraction" / "turn-pass" / "validated").exists()

    for unit in units[1:]:
        filename = f"{unit.candidate_index:04d}-{unit.turn_index:04d}.json"
        (raw_dir / filename).write_text(json.dumps({"candidate_id": unit.candidate_id, "turn_index": unit.turn_index, "context_completions": [], "knowledge": []}, ensure_ascii=False), encoding="utf-8")
    (raw_dir / "extra.json").write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="extra raw output"):
        main(["validate-turns", "--manifest", str(manifest_path), "--raw-dir", str(raw_dir), "--output-dir", str(tmp_path / "published")])


def test_validate_turns_writes_nothing_when_one_output_is_invalid(tmp_path: Path) -> None:
    prepared = tmp_path / "prepared"
    manifest_path = prepare_turn_payloads(DATASET, prepared, PROMPT, SEGMENTS)
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    for unit in load_turn_units(DATASET):
        filename = f"{unit.candidate_index:04d}-{unit.turn_index:04d}.json"
        data: dict[str, object] = {"candidate_id": unit.candidate_id, "turn_index": unit.turn_index, "context_completions": [], "knowledge": []}
        if filename == "0000-0000.json":
            data["candidate_id"] = "wrong-candidate"
        (raw_dir / filename).write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(ValueError, match="candidate_id"):
        main(["validate-turns", "--manifest", str(manifest_path), "--raw-dir", str(raw_dir), "--output-dir", str(tmp_path / "published")])
    assert not (tmp_path / "published" / "knowledge-extraction" / "turn-pass" / "validated").exists()


def test_validate_turn_batch_reports_the_failing_raw_filename(tmp_path: Path) -> None:
    manifest_path = prepare_turn_payloads(DATASET, tmp_path / "prepared", PROMPT, SEGMENTS)
    raw_dir = tmp_path / "raw"
    _write_empty_raw_outputs(raw_dir)
    invalid = raw_dir / "0000-0000.json"
    value = json.loads(invalid.read_text(encoding="utf-8"))
    value["candidate_id"] = "wrong-candidate"
    invalid.write_text(json.dumps(value), encoding="utf-8")

    with pytest.raises(ValueError, match="0000-0000.json"):
        validate_turn_batch(manifest_path, raw_dir, tmp_path / "published")


def _write_empty_raw_outputs(raw_dir: Path) -> None:
    raw_dir.mkdir()
    for unit in load_turn_units(DATASET):
        filename = f"{unit.candidate_index:04d}-{unit.turn_index:04d}.json"
        raw_dir.joinpath(filename).write_text(
            json.dumps({"candidate_id": unit.candidate_id, "turn_index": unit.turn_index, "context_completions": [], "knowledge": []}, ensure_ascii=False),
            encoding="utf-8",
        )


def test_validate_turn_batch_publishes_validated_files_and_manifest_together(tmp_path: Path) -> None:
    manifest_path = prepare_turn_payloads(DATASET, tmp_path / "prepared", PROMPT, SEGMENTS)
    raw_dir = tmp_path / "raw"
    _write_empty_raw_outputs(raw_dir)

    publication = validate_turn_batch(manifest_path, raw_dir, tmp_path / "published")

    validated = tmp_path / "published" / "knowledge-extraction" / "turn-pass" / "validated"
    assert publication == validated / "manifest.json"
    assert publication.is_file()
    assert len(list(validated.glob("[0-9][0-9][0-9][0-9]-[0-9][0-9][0-9][0-9].json"))) == 43
    assert not (validated.parent / "validated-manifest.json").exists()
    aggregate = json.loads(publication.read_text(encoding="utf-8"))
    assert all(item["raw_sha256_before"] == item["raw_sha256_after"] for item in aggregate["turns"])


def test_validate_turn_batch_allows_raw_and_validated_as_siblings_under_output_root(tmp_path: Path) -> None:
    manifest_path = prepare_turn_payloads(DATASET, tmp_path, PROMPT, SEGMENTS)
    raw_dir = tmp_path / "knowledge-extraction" / "turn-pass" / "raw"
    _write_empty_raw_outputs(raw_dir)

    publication = validate_turn_batch(manifest_path, raw_dir, tmp_path)

    assert publication == tmp_path / "knowledge-extraction" / "turn-pass" / "validated" / "manifest.json"
    assert publication.is_file()


def test_validate_turn_batch_cleans_staging_when_manifest_write_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    manifest_path = prepare_turn_payloads(DATASET, tmp_path / "prepared", PROMPT, SEGMENTS)
    raw_dir = tmp_path / "raw"
    _write_empty_raw_outputs(raw_dir)

    def fail_manifest_write(path: Path, value: object) -> None:
        if path.name == "manifest.json":
            raise OSError("injected manifest write failure")
        path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    monkeypatch.setattr(turn_pass, "_write_json", fail_manifest_write)

    with pytest.raises(OSError, match="injected manifest"):
        validate_turn_batch(manifest_path, raw_dir, tmp_path / "published")
    root = tmp_path / "published" / "knowledge-extraction" / "turn-pass"
    assert not (root / "validated").exists()
    assert not list(root.glob("validated-*"))


def test_validate_turn_batch_preserves_manifest_write_error_when_cleanup_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    manifest_path = prepare_turn_payloads(DATASET, tmp_path / "prepared", PROMPT, SEGMENTS)
    raw_dir = tmp_path / "raw"
    _write_empty_raw_outputs(raw_dir)

    def fail_manifest_write(path: Path, value: object) -> None:
        if path.name == "manifest.json":
            raise OSError("original manifest write failure")
        path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def fail_cleanup(path: Path, *args: object, **kwargs: object) -> None:
        raise RuntimeError("cleanup failure")

    monkeypatch.setattr(turn_pass, "_write_json", fail_manifest_write)
    monkeypatch.setattr(turn_pass.shutil, "rmtree", fail_cleanup)

    with pytest.raises(OSError, match="original manifest"):
        validate_turn_batch(manifest_path, raw_dir, tmp_path / "published")


@pytest.mark.parametrize(
    ("prompt_name", "required_phrase"),
    [
        ("turn_knowledge_extraction.md", "exactly one user message"),
        ("dialogue_reconciliation.md", "A-stage records as immutable"),
        ("knowledge_keyword_extraction.md", "Do not emit vocabulary IDs"),
        ("vocabulary_candidate_ranking.md", "supplied whitelist IDs"),
    ],
)
def test_all_prompts_have_required_sections_and_key_boundaries(prompt_name: str, required_phrase: str) -> None:
    text = (PROMPT.parent / prompt_name).read_text(encoding="utf-8")
    for heading in (
        "Input Boundary", "Output Contract", "Completeness Checklist", "Evidence Rules",
        "Epistemic Rules", "Forbidden Behavior", "Final Self-Check",
    ):
        assert f"## {heading}" in text
    assert required_phrase in text
    assert "old KEOL" in text and "custom KE" in text


def test_candidate_namespaces_are_nonempty_and_slug_collision_safe() -> None:
    assert candidate_namespace("A-B") != candidate_namespace("A_B")
    assert candidate_namespace("中文")


def test_prepare_turn_payloads_rejects_existing_batch_and_cleans_staging_on_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    prepare_turn_payloads(DATASET, tmp_path, PROMPT, SEGMENTS)
    with pytest.raises(ValueError, match="already exists"):
        prepare_turn_payloads(DATASET, tmp_path, PROMPT, SEGMENTS)

    failing = tmp_path / "failing"
    original = turn_pass._write_json

    def fail_manifest(path: Path, value: object) -> None:
        if path.name == "manifest.json":
            raise OSError("injected preparation failure")
        original(path, value)

    monkeypatch.setattr(turn_pass, "_write_json", fail_manifest)
    with pytest.raises(OSError, match="injected preparation"):
        prepare_turn_payloads(DATASET, failing, PROMPT, SEGMENTS)
    root = failing / "knowledge-extraction" / "turn-pass"
    assert not (root / "prepared").exists()
    assert not list(root.glob("prepared-*"))


@pytest.mark.parametrize("tamper", ["user", "agent", "schema", "coordinates", "canonical_filename"])
def test_validate_turn_batch_rejects_tampered_preparation_provenance(tmp_path: Path, tamper: str) -> None:
    manifest_path = prepare_turn_payloads(DATASET, tmp_path / "prepared", PROMPT, SEGMENTS)
    raw_dir = tmp_path / "raw"
    _write_empty_raw_outputs(raw_dir)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    payload_path = manifest_path.parent / "payloads" / "0000-0000.json"
    if tamper == "canonical_filename":
        manifest["turns"][0]["canonical_filename"] = "tampered.json"
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    else:
        payload = json.loads(payload_path.read_text(encoding="utf-8"))
        if tamper == "user":
            payload["user"] += " tampered"
        elif tamper == "agent":
            payload["agent"] += " tampered"
        elif tamper == "schema":
            payload["output_contract"]["title"] = "tampered"
        else:
            payload["source_coordinates"]["user"] = "/tampered"
        payload_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    with pytest.raises(ValueError):
        validate_turn_batch(manifest_path, raw_dir, tmp_path / "published")


def test_validate_turn_batch_rejects_tampered_prompt_and_overlapping_paths(tmp_path: Path) -> None:
    prompt = tmp_path / "prompt.md"
    prompt.write_text(PROMPT.read_text(encoding="utf-8"), encoding="utf-8")
    manifest_path = prepare_turn_payloads(DATASET, tmp_path / "prepared", prompt, SEGMENTS)
    raw_dir = tmp_path / "raw"
    _write_empty_raw_outputs(raw_dir)
    with pytest.raises(ValueError, match="disjoint"):
        validate_turn_batch(manifest_path, raw_dir, raw_dir)
    with pytest.raises(ValueError, match="disjoint"):
        validate_turn_batch(manifest_path, raw_dir, raw_dir / "nested")
    prompt.write_text(prompt.read_text(encoding="utf-8") + "\ntampered", encoding="utf-8")
    with pytest.raises(ValueError, match="prompt SHA256"):
        validate_turn_batch(manifest_path, raw_dir, tmp_path / "published")


def test_validate_turn_batch_rejects_other_candidate_ids_only_in_semantic_text(tmp_path: Path) -> None:
    manifest_path = prepare_turn_payloads(DATASET, tmp_path / "prepared", PROMPT, SEGMENTS)
    raw_dir = tmp_path / "raw"
    _write_empty_raw_outputs(raw_dir)
    units = load_turn_units(DATASET)
    first = units[0]
    other = next(unit for unit in units if unit.candidate_id != first.candidate_id)
    output = raw_output(first.candidate_id, first.turn_index, first.user, first.agent)
    item = output["knowledge"][0]  # type: ignore[index]
    item["statement"] = f"Reference {other.candidate_id} is forbidden here."
    item["evidence"] = [{"turn_index": first.turn_index, "message": "user", "occurrence_index": 0, "quote": first.user}]
    (raw_dir / "0000-0000.json").write_text(json.dumps(output, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(ValueError, match="another candidate"):
        validate_turn_batch(manifest_path, raw_dir, tmp_path / "published")


def test_prepare_turn_payloads_rejects_missing_source_segments_atomically(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="source-segments|source segments"):
        prepare_turn_payloads(DATASET, tmp_path, PROMPT, tmp_path / "missing-source-segments.json")
    root = tmp_path / "knowledge-extraction" / "turn-pass"
    assert not (root / "prepared").exists()


def test_validate_turn_batch_rejects_tampered_source_segments_hash_atomically(tmp_path: Path) -> None:
    segments = tmp_path / "source-segments.json"
    segments.write_bytes(SEGMENTS.read_bytes())
    manifest_path = prepare_turn_payloads(DATASET, tmp_path / "prepared", PROMPT, segments)
    raw_dir = tmp_path / "raw"
    _write_empty_raw_outputs(raw_dir)
    segments.write_text(segments.read_text(encoding="utf-8") + " ", encoding="utf-8")

    with pytest.raises(ValueError, match="source segments SHA256"):
        validate_turn_batch(manifest_path, raw_dir, tmp_path / "published")
    assert not (tmp_path / "published" / "knowledge-extraction" / "turn-pass" / "validated").exists()


def test_validate_turn_batch_rejects_payload_spans_that_differ_from_sidecar(tmp_path: Path) -> None:
    manifest_path = prepare_turn_payloads(DATASET, tmp_path / "prepared", PROMPT, SEGMENTS)
    raw_dir = tmp_path / "raw"
    _write_empty_raw_outputs(raw_dir)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    filename = "0006-0001.json"
    payload_path = manifest_path.parent / "payloads" / filename
    payload = json.loads(payload_path.read_text(encoding="utf-8"))
    quote = "return_delivered_order_items"
    start = payload["agent"].index(quote)
    payload["tool_result_spans"] = [{
        "quote": quote, "occurrence_index": 0, "marker_occurrence_index": 0,
        "start": start, "end": start + len(quote),
    }]
    payload_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    entry = next(item for item in manifest["turns"] if item["canonical_filename"] == filename)
    entry["payload_sha256"] = hashlib.sha256(payload_path.read_bytes()).hexdigest()
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(ValueError, match="source segment|tool_result_spans|tool result span"):
        validate_turn_batch(manifest_path, raw_dir, tmp_path / "published")
    assert not (tmp_path / "published" / "knowledge-extraction" / "turn-pass" / "validated").exists()
