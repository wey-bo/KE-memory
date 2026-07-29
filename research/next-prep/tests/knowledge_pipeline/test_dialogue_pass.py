from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pytest

import knowledge_pipeline.dialogue_pass as dialogue_pass
from knowledge_pipeline.cli import main
from knowledge_pipeline.evidence import resolve_evidence
from knowledge_pipeline.models import DialoguePassOutput
from knowledge_pipeline.source import load_turn_units
from knowledge_pipeline.turn_pass import candidate_namespace, prepare_turn_payloads, validate_turn_batch


ROOT = Path(__file__).resolve().parents[2]
DATASET = ROOT / "data" / "gold-candidates" / "KE-test.json"
PROMPT = ROOT / "knowledge-extraction" / "prompts" / "dialogue_reconciliation.md"
TURN_PROMPT = ROOT / "knowledge-extraction" / "prompts" / "turn_knowledge_extraction.md"
SEGMENTS = ROOT / "knowledge-extraction" / "source-segments.json"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _schema_sha256() -> str:
    encoded = json.dumps(
        DialoguePassOutput.model_json_schema(), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _stage_first_pass(tmp_path: Path, segments: Path = SEGMENTS) -> Path:
    root = tmp_path / "first-pass" / "knowledge-extraction" / "turn-pass"
    output_root = tmp_path / "first-pass"
    prepared_manifest = prepare_turn_payloads(DATASET, output_root, TURN_PROMPT, segments)
    raw_dir = root / "raw"
    raw_dir.mkdir()
    for unit in load_turn_units(DATASET):
        raw_dir.joinpath(f"{unit.candidate_index:04d}-{unit.turn_index:04d}.json").write_text(
            json.dumps({
                "candidate_id": unit.candidate_id,
                "turn_index": unit.turn_index,
                "context_completions": [],
                "knowledge": [],
            }),
            encoding="utf-8",
        )
    return validate_turn_batch(prepared_manifest, raw_dir, output_root)


def _prepare(tmp_path: Path, *, prompt: Path = PROMPT, segments: Path = SEGMENTS) -> Path:
    return dialogue_pass.prepare_dialogue_payloads(
        DATASET, _stage_first_pass(tmp_path, segments), tmp_path / "dialogues", prompt
    )


def _synthetic_payload() -> dict[str, object]:
    candidate_id = "candidate-alpha"
    namespace = candidate_namespace(candidate_id)
    agent_with_result = "[工具调用] save() [工具结果] preference saved"
    result_quote = "preference saved"
    result_start = agent_with_result.index(result_quote)
    turns = [
        {
            "turn_index": 0,
            "user": "I preferred tea yesterday.",
            "agent": "I noted that preference.",
            "source_coordinates": {
                "user": "/candidates/0/turns/0/user",
                "agent": "/candidates/0/turns/0/agent",
            },
            "tool_result_spans": [],
        },
        {
            "turn_index": 1,
            "user": "I prefer coffee now.",
            "agent": agent_with_result,
            "source_coordinates": {
                "user": "/candidates/0/turns/1/user",
                "agent": "/candidates/0/turns/1/agent",
            },
            "tool_result_spans": [{
                "quote": result_quote,
                "occurrence_index": 0,
                "marker_occurrence_index": 0,
                "start": result_start,
                "end": result_start + len(result_quote),
            }],
        },
    ]
    a_knowledge = [
        {"knowledge_id": f"K_{namespace}_000_001", "candidate_id": candidate_id},
        {"knowledge_id": f"K_{namespace}_001_001", "candidate_id": candidate_id},
    ]
    return {
        "prompt_version": "dialogue-reconciliation-v1",
        "candidate_id": candidate_id,
        "candidate_index": 0,
        "source": "synthetic",
        "candidate_namespace": namespace,
        "conversation": turns,
        "first_pass_records": [
            {
                "turn_index": 0,
                "canonical_filename": "0000-0000.json",
                "sha256": "0" * 64,
                "output": {"candidate_id": candidate_id, "turn_index": 0, "knowledge": a_knowledge[:1]},
            },
            {
                "turn_index": 1,
                "canonical_filename": "0000-0001.json",
                "sha256": "1" * 64,
                "output": {"candidate_id": candidate_id, "turn_index": 1, "knowledge": a_knowledge[1:]},
            },
        ],
        "knowledge_id_prefix": f"D_{namespace}_",
        "operation_id_prefix": f"R_{namespace}_",
        "output_contract": DialoguePassOutput.model_json_schema(),
        "prompt_sha256": "2" * 64,
        "output_contract_sha256": _schema_sha256(),
        "source_segments_sha256": "7" * 64,
    }


def _new_knowledge(payload: dict[str, object], **overrides: object) -> dict[str, object]:
    namespace = str(payload["candidate_namespace"])
    value: dict[str, object] = {
        "knowledge_id": f"D_{namespace}_001",
        "candidate_id": payload["candidate_id"],
        "statement": "The user now prefers coffee.",
        "subject": "user",
        "predicate": "prefers",
        "object": "coffee",
        "qualifiers": {"modality": "preferred", "polarity": "positive"},
        "source_status": "user_reported",
        "derivation": "explicit",
        "evidence": [
            {
                "turn_index": 1,
                "message": "user",
                "occurrence_index": 0,
                "quote": "I prefer coffee now.",
            }
        ],
        "inference_basis": None,
        "confidence": 0.95,
    }
    value.update(overrides)
    return value


def _operation(payload: dict[str, object], **overrides: object) -> dict[str, object]:
    namespace = str(payload["candidate_namespace"])
    target = payload["first_pass_records"][0]["output"]["knowledge"][0]["knowledge_id"]  # type: ignore[index]
    value: dict[str, object] = {
        "operation_id": f"R_{namespace}_001",
        "candidate_id": payload["candidate_id"],
        "operation": "correct",
        "targets": [target],
        "replacement": f"D_{namespace}_001",
        "reason": "The later user report changes the preference.",
        "evidence": [
            {
                "turn_index": 1,
                "message": "user",
                "occurrence_index": 0,
                "quote": "I prefer coffee now.",
                "evidence_role": "user_reported",
            }
        ],
        "confidence": 0.94,
    }
    value.update(overrides)
    return value


def _raw(payload: dict[str, object]) -> dict[str, object]:
    return {
        "candidate_id": payload["candidate_id"],
        "new_knowledge": [_new_knowledge(payload)],
        "operations": [_operation(payload)],
    }


def _a_ids(payload: dict[str, object]) -> tuple[str, str]:
    return (
        payload["first_pass_records"][0]["output"]["knowledge"][0]["knowledge_id"],  # type: ignore[index]
        payload["first_pass_records"][1]["output"]["knowledge"][0]["knowledge_id"],  # type: ignore[index]
    )


def _write_empty_raw_batch(manifest_path: Path, raw_dir: Path) -> None:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    raw_dir.mkdir(parents=True)
    for item in manifest["candidates"]:
        raw_dir.joinpath(item["canonical_filename"]).write_text(
            json.dumps({"candidate_id": item["candidate_id"], "new_knowledge": [], "operations": []}),
            encoding="utf-8",
        )


def test_prepare_dialogue_payloads_contains_complete_conversations_and_all_a_stage_hashes(tmp_path: Path) -> None:
    manifest_path = _prepare(tmp_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    payloads = manifest_path.parent / "payloads"
    dataset = json.loads(DATASET.read_text(encoding="utf-8"))

    assert len(manifest["candidates"]) == 10
    assert len(list(payloads.glob("*.json"))) == 10
    assert manifest["source_sha256"] == _sha256(DATASET)
    assert manifest["first_pass_manifest_sha256"] == _sha256(
        Path(manifest["first_pass_manifest_file"])
    )
    for candidate, entry in zip(dataset["candidates"], manifest["candidates"], strict=True):
        payload = json.loads((payloads / entry["canonical_filename"]).read_text(encoding="utf-8"))
        assert payload["candidate_id"] == candidate["id"]
        assert [
            {"user": turn["user"], "agent": turn["agent"]}
            for turn in payload["conversation"]
        ] == candidate["turns"]
        assert all(record["sha256"] for record in payload["first_pass_records"])
        assert len(payload["first_pass_records"]) == len(candidate["turns"])
        assert payload["knowledge_id_prefix"] == f"D_{payload['candidate_namespace']}_"
        assert payload["operation_id_prefix"] == f"R_{payload['candidate_namespace']}_"
        assert payload["prompt_sha256"] == manifest["prompt_sha256"]
        assert payload["output_contract_sha256"] == manifest["output_contract_sha256"]
        assert payload["source_segments_sha256"] == manifest["source_segments_sha256"]
        assert all("tool_result_spans" in turn for turn in payload["conversation"])
        text = json.dumps(payload, ensure_ascii=False).lower()
        assert "old keol" not in text and "custom ke" not in text


def test_prepare_dialogue_payloads_rejects_incomplete_or_tampered_first_pass(tmp_path: Path) -> None:
    manifest_path = _stage_first_pass(tmp_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    missing = manifest_path.parent / manifest["turns"][-1]["validated_file"]
    missing.unlink()
    with pytest.raises(ValueError, match="43|missing"):
        dialogue_pass.prepare_dialogue_payloads(DATASET, manifest_path, tmp_path / "missing", PROMPT)

    manifest_path = _stage_first_pass(tmp_path / "tampered")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["turns"][0]["payload_sha256"] = "0" * 64
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="payload|SHA256|provenance"):
        dialogue_pass.prepare_dialogue_payloads(DATASET, manifest_path, tmp_path / "tampered-out", PROMPT)


def test_prepare_dialogue_payloads_verifies_available_raw_provenance(tmp_path: Path) -> None:
    manifest_path = _stage_first_pass(tmp_path)
    raw_file = manifest_path.parent.parent / "raw" / "0000-0000.json"
    raw_file.write_text(raw_file.read_text(encoding="utf-8") + " ", encoding="utf-8")

    with pytest.raises(ValueError, match="raw.*SHA256|raw provenance"):
        dialogue_pass.prepare_dialogue_payloads(DATASET, manifest_path, tmp_path / "dialogues", PROMPT)


def test_prepare_dialogue_payloads_requires_raw_first_pass_outputs(tmp_path: Path) -> None:
    manifest_path = _stage_first_pass(tmp_path)
    raw_dir = manifest_path.parent.parent / "raw"
    raw_dir.rename(raw_dir.with_name("raw-missing"))

    with pytest.raises(ValueError, match="raw.*required|raw.*missing"):
        dialogue_pass.prepare_dialogue_payloads(DATASET, manifest_path, tmp_path / "dialogues", PROMPT)


def test_prepare_dialogue_payloads_replays_raw_to_reject_valid_shaped_validated_tampering(
    tmp_path: Path,
) -> None:
    manifest_path = _stage_first_pass(tmp_path)
    unit = load_turn_units(DATASET)[0]
    validated_file = manifest_path.parent / "0000-0000.json"
    validated = json.loads(validated_file.read_text(encoding="utf-8"))
    evidence = resolve_evidence(
        unit.candidate_id, unit.turn_index, unit.user, "user", unit.user, 0, "user_reported"
    )
    validated["knowledge"].append({
        "knowledge_id": f"K_{candidate_namespace(unit.candidate_id)}_000_001",
        "candidate_id": unit.candidate_id,
        "statement": "A valid-shaped but untrusted statement.",
        "subject": "user",
        "predicate": "reported",
        "object": unit.user,
        "qualifiers": {"modality": "asserted", "polarity": "positive"},
        "source_status": "user_reported",
        "derivation": "explicit",
        "evidence": [evidence.model_dump(mode="json")],
        "inference_basis": None,
        "confidence": 0.5,
    })
    validated_file.write_text(json.dumps(validated, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(ValueError, match="replayed raw|raw replay|validated A-stage.*differs"):
        dialogue_pass.prepare_dialogue_payloads(DATASET, manifest_path, tmp_path / "dialogues", PROMPT)


def test_prepare_dialogue_payloads_rejects_first_pass_raw_manifest_hash_tampering(tmp_path: Path) -> None:
    manifest_path = _stage_first_pass(tmp_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["turns"][0]["raw_sha256_before"] = "3" * 64
    manifest["turns"][0]["raw_sha256_after"] = "3" * 64
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(ValueError, match="raw.*SHA256|raw provenance"):
        dialogue_pass.prepare_dialogue_payloads(DATASET, manifest_path, tmp_path / "dialogues", PROMPT)


def test_prepare_dialogue_payloads_is_immutable_and_atomic(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    manifest_path = _prepare(tmp_path)
    second_first_pass = _stage_first_pass(tmp_path / "second")
    with pytest.raises(ValueError, match="already exists"):
        dialogue_pass.prepare_dialogue_payloads(DATASET, second_first_pass, tmp_path / "dialogues", PROMPT)

    original = dialogue_pass._write_json

    def fail_manifest(path: Path, value: object) -> None:
        if path.name == "manifest.json":
            raise OSError("injected dialogue preparation failure")
        original(path, value)

    monkeypatch.setattr(dialogue_pass, "_write_json", fail_manifest)
    failing_first_pass = _stage_first_pass(tmp_path / "failing")
    with pytest.raises(OSError, match="injected dialogue"):
        dialogue_pass.prepare_dialogue_payloads(DATASET, failing_first_pass, tmp_path / "failed", PROMPT)
    root = tmp_path / "failed" / "knowledge-extraction" / "dialogue-pass"
    assert not (root / "prepared").exists()
    assert not list(root.glob("prepared-*"))


def test_validate_dialogue_output_materializes_evidence_and_preserves_raw() -> None:
    payload = _synthetic_payload()
    raw = _raw(payload)
    before = copy.deepcopy(raw)

    validated = dialogue_pass.validate_dialogue_output(raw, payload)

    assert raw == before
    assert validated["new_knowledge"][0]["evidence"][0]["start"] == 0
    assert validated["new_knowledge"][0]["evidence"][0]["candidate_id"] == "candidate-alpha"
    assert validated["operations"][0]["evidence"][0]["message"] == "user"


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda raw, payload: raw.update(candidate_id="candidate-beta"), "candidate_id"),
        (lambda raw, payload: raw["operations"][0].update(targets=["unknown"]), "target"),
        (lambda raw, payload: raw["operations"][0].update(replacement="unknown"), "replacement"),
        (lambda raw, payload: raw["operations"][0].update(replacement=None), "replacement"),
        (lambda raw, payload: raw.update(operations=[]), "orphan"),
        (lambda raw, payload: raw["new_knowledge"].append(copy.deepcopy(raw["new_knowledge"][0])), "unique"),
        (lambda raw, payload: raw["operations"].append(copy.deepcopy(raw["operations"][0])), "unique"),
    ],
)
def test_validate_dialogue_output_rejects_reference_and_id_failures(mutate, message: str) -> None:
    payload = _synthetic_payload()
    raw = _raw(payload)
    mutate(raw, payload)
    with pytest.raises(ValueError, match=message):
        dialogue_pass.validate_dialogue_output(raw, payload)


def test_validate_dialogue_output_rejects_cross_candidate_target() -> None:
    payload = _synthetic_payload()
    raw = _raw(payload)
    raw["operations"][0]["targets"] = [
        f"K_{candidate_namespace('candidate-beta')}_000_001"
    ]
    with pytest.raises(ValueError, match="cross-candidate|target"):
        dialogue_pass.validate_dialogue_output(raw, payload)


@pytest.mark.parametrize("case", ["d_gap", "d_order", "d_prefix", "r_gap", "r_order", "r_prefix"])
def test_validate_dialogue_output_rejects_non_contiguous_or_wrong_scoped_ids(case: str) -> None:
    payload = _synthetic_payload()
    raw = _raw(payload)
    namespace = str(payload["candidate_namespace"])
    second_knowledge = copy.deepcopy(raw["new_knowledge"][0])
    second_knowledge["knowledge_id"] = f"D_{namespace}_002"
    second_operation = copy.deepcopy(raw["operations"][0])
    second_operation["operation_id"] = f"R_{namespace}_002"
    second_operation["replacement"] = second_knowledge["knowledge_id"]
    raw["new_knowledge"].append(second_knowledge)
    raw["operations"].append(second_operation)
    if case == "d_gap":
        second_knowledge["knowledge_id"] = f"D_{namespace}_003"
        second_operation["replacement"] = second_knowledge["knowledge_id"]
    elif case == "d_order":
        raw["new_knowledge"].reverse()
    elif case == "d_prefix":
        raw["new_knowledge"][0]["knowledge_id"] = "D_other_001"
        raw["operations"][0]["replacement"] = "D_other_001"
    elif case == "r_gap":
        second_operation["operation_id"] = f"R_{namespace}_003"
    elif case == "r_order":
        raw["operations"].reverse()
    else:
        raw["operations"][0]["operation_id"] = "R_other_001"

    with pytest.raises(ValueError, match="contiguous|candidate scoped"):
        dialogue_pass.validate_dialogue_output(raw, payload)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("turn_index", 9, "turn_index"),
        ("quote", "missing quote", "quote occurrence"),
        ("message", "agent", "user_reported"),
    ],
)
def test_validate_dialogue_output_rejects_invalid_new_knowledge_evidence(
    field: str, value: object, message: str
) -> None:
    payload = _synthetic_payload()
    raw = _raw(payload)
    raw["new_knowledge"][0]["evidence"][0][field] = value
    with pytest.raises(ValueError, match=message):
        dialogue_pass.validate_dialogue_output(raw, payload)


def test_tool_observed_requires_content_after_explicit_tool_result() -> None:
    payload = _synthetic_payload()
    raw = _raw(payload)
    item = raw["new_knowledge"][0]
    item.update(
        source_status="tool_observed",
        statement="The tool saved the preference.",
        evidence=[
            {"turn_index": 1, "message": "agent", "occurrence_index": 0, "quote": "preference saved"}
        ],
    )
    assert dialogue_pass.validate_dialogue_output(raw, payload)["new_knowledge"][0]["source_status"] == "tool_observed"

    item["evidence"] = [
        {"turn_index": 1, "message": "agent", "occurrence_index": 0, "quote": "[工具结果]"}
    ]
    with pytest.raises(ValueError, match="tool_observed"):
        dialogue_pass.validate_dialogue_output(raw, payload)

    item["source_status"] = "agent_generated"
    item["evidence"] = [
        {"turn_index": 1, "message": "agent", "occurrence_index": 0, "quote": "preference saved"}
    ]
    with pytest.raises(ValueError, match="agent_generated"):
        dialogue_pass.validate_dialogue_output(raw, payload)
    item["evidence"] = [
        {"turn_index": 1, "message": "agent", "occurrence_index": 0, "quote": "save()"}
    ]
    dialogue_pass.validate_dialogue_output(raw, payload)


def test_correct_and_add_replacements_require_new_dialogue_knowledge() -> None:
    payload = _synthetic_payload()
    existing = payload["first_pass_records"][1]["output"]["knowledge"][0]["knowledge_id"]
    for operation in ("correct", "add"):
        raw = _raw(payload)
        raw["operations"][0].update(
            operation=operation,
            targets=[] if operation == "add" else raw["operations"][0]["targets"],
            replacement=existing,
        )
        with pytest.raises(ValueError, match="new dialogue knowledge"):
            dialogue_pass.validate_dialogue_output(raw, payload)


def test_supersede_replacement_may_reference_existing_same_candidate_knowledge() -> None:
    payload = _synthetic_payload()
    raw = {"candidate_id": payload["candidate_id"], "new_knowledge": [], "operations": [_operation(payload)]}
    existing = payload["first_pass_records"][1]["output"]["knowledge"][0]["knowledge_id"]
    raw["operations"][0].update(operation="supersede", replacement=existing)
    dialogue_pass.validate_dialogue_output(raw, payload)


def test_state_operations_may_not_assign_the_same_a_stage_target_twice() -> None:
    payload = _synthetic_payload()
    raw = _raw(payload)
    namespace = str(payload["candidate_namespace"])
    duplicate = copy.deepcopy(raw["operations"][0])
    duplicate.update(operation_id=f"R_{namespace}_002", operation="supersede", replacement=None)
    raw["operations"].append(duplicate)

    with pytest.raises(ValueError, match="state operation|terminal assignment|at most one"):
        dialogue_pass.validate_dialogue_output(raw, payload)


def test_correct_cannot_target_new_dialogue_knowledge() -> None:
    payload = _synthetic_payload()
    raw = _raw(payload)
    dialogue_id = raw["new_knowledge"][0]["knowledge_id"]
    raw["operations"][0]["targets"] = [dialogue_id]

    with pytest.raises(ValueError, match="A-stage"):
        dialogue_pass.validate_dialogue_output(raw, payload)


def test_conflict_cannot_target_corrected_or_superseded_knowledge() -> None:
    payload = _synthetic_payload()
    raw = _raw(payload)
    namespace = str(payload["candidate_namespace"])
    target = raw["operations"][0]["targets"][0]
    conflict = copy.deepcopy(raw["operations"][0])
    conflict.update(
        operation_id=f"R_{namespace}_002",
        operation="conflict",
        targets=[target, _a_ids(payload)[1]],
        replacement=None,
    )
    raw["operations"].append(conflict)

    with pytest.raises(ValueError, match="conflict.*corrected|conflict.*superseded"):
        dialogue_pass.validate_dialogue_output(raw, payload)


def test_supersede_rejects_self_reference() -> None:
    payload = _synthetic_payload()
    target = _a_ids(payload)[0]
    raw = {"candidate_id": payload["candidate_id"], "new_knowledge": [], "operations": [_operation(payload)]}
    raw["operations"][0].update(operation="supersede", targets=[target], replacement=target)

    with pytest.raises(ValueError, match="self-reference"):
        dialogue_pass.validate_dialogue_output(raw, payload)


@pytest.mark.parametrize("cycle", [False, True])
def test_supersede_rejects_replacement_chains_and_cycles(cycle: bool) -> None:
    payload = _synthetic_payload()
    first_a, second_a = _a_ids(payload)
    namespace = str(payload["candidate_namespace"])
    first = _operation(payload, operation="supersede", targets=[first_a], replacement=second_a)
    second = _operation(
        payload,
        operation_id=f"R_{namespace}_002",
        operation="supersede",
        targets=[second_a],
        replacement=first_a if cycle else f"D_{namespace}_001",
    )
    raw = {
        "candidate_id": payload["candidate_id"],
        "new_knowledge": [] if cycle else [_new_knowledge(payload)],
        "operations": [first, second],
    }

    with pytest.raises(ValueError, match="chain|cycle|replacement.*target"):
        dialogue_pass.validate_dialogue_output(raw, payload)


def test_supersede_accepts_active_a_stage_or_new_dialogue_replacement() -> None:
    payload = _synthetic_payload()
    first_a, second_a = _a_ids(payload)
    active_a = {
        "candidate_id": payload["candidate_id"],
        "new_knowledge": [],
        "operations": [_operation(payload, operation="supersede", targets=[first_a], replacement=second_a)],
    }
    dialogue = _raw(payload)
    dialogue["operations"][0]["operation"] = "supersede"

    dialogue_pass.validate_dialogue_output(active_a, payload)
    dialogue_pass.validate_dialogue_output(dialogue, payload)


def test_operation_evidence_preserves_declared_tool_role_and_may_mix_roles() -> None:
    payload = _synthetic_payload()
    raw = _raw(payload)
    raw["operations"][0]["evidence"] = [
        {
            "turn_index": 1,
            "message": "user",
            "occurrence_index": 0,
            "quote": "I prefer coffee now.",
            "evidence_role": "user_reported",
        },
        {
            "turn_index": 1,
            "message": "agent",
            "occurrence_index": 0,
            "quote": "save()",
            "evidence_role": "agent_generated",
        },
        {
            "turn_index": 1,
            "message": "agent",
            "occurrence_index": 0,
            "quote": "preference saved",
            "evidence_role": "tool_observed",
        },
    ]

    evidence = dialogue_pass.validate_dialogue_output(raw, payload)["operations"][0]["evidence"]
    assert [item["evidence_role"] for item in evidence] == [
        "user_reported", "agent_generated", "tool_observed"
    ]


@pytest.mark.parametrize(
    ("message", "quote", "role"),
    [
        ("user", "I prefer coffee now.", "agent_generated"),
        ("user", "I prefer coffee now.", "tool_observed"),
        ("agent", "save()", "tool_observed"),
        ("agent", "preference saved", "agent_generated"),
        ("agent", "[工具结果]", "tool_observed"),
    ],
)
def test_operation_evidence_rejects_mismatched_declared_role(
    message: str, quote: str, role: str
) -> None:
    payload = _synthetic_payload()
    raw = _raw(payload)
    raw["operations"][0]["evidence"] = [{
        "turn_index": 1,
        "message": message,
        "occurrence_index": 0,
        "quote": quote,
        "evidence_role": role,
    }]

    with pytest.raises(ValueError, match="evidence_role|user_reported|agent_generated|tool_observed"):
        dialogue_pass.validate_dialogue_output(raw, payload)


def test_validate_dialogue_batch_rejects_missing_extra_and_tampered_inputs(tmp_path: Path) -> None:
    manifest_path = _prepare(tmp_path)
    raw_dir = tmp_path / "raw"
    _write_empty_raw_batch(manifest_path, raw_dir)
    first = sorted(raw_dir.glob("*.json"))[0]
    first.unlink()
    with pytest.raises(ValueError, match="missing raw"):
        dialogue_pass.validate_dialogue_batch(manifest_path, raw_dir, tmp_path / "published")
    first.write_text("{}", encoding="utf-8")
    (raw_dir / "extra.json").write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="extra raw"):
        dialogue_pass.validate_dialogue_batch(manifest_path, raw_dir, tmp_path / "published")

    (raw_dir / "extra.json").unlink()
    payload_path = manifest_path.parent / "payloads" / "0000.json"
    payload_path.write_text(payload_path.read_text(encoding="utf-8") + " ", encoding="utf-8")
    with pytest.raises(ValueError, match="payload.*SHA256"):
        dialogue_pass.validate_dialogue_batch(manifest_path, raw_dir, tmp_path / "published")


def test_validate_dialogue_batch_rejects_source_prompt_schema_and_first_pass_tampering(tmp_path: Path) -> None:
    prompt = tmp_path / "dialogue.md"
    prompt.write_text(PROMPT.read_text(encoding="utf-8"), encoding="utf-8")
    manifest_path = _prepare(tmp_path, prompt=prompt)
    raw_dir = tmp_path / "raw"
    _write_empty_raw_batch(manifest_path, raw_dir)

    prompt.write_text(prompt.read_text(encoding="utf-8") + "tampered", encoding="utf-8")
    with pytest.raises(ValueError, match="prompt SHA256"):
        dialogue_pass.validate_dialogue_batch(manifest_path, raw_dir, tmp_path / "prompt-out")
    prompt.write_text(PROMPT.read_text(encoding="utf-8"), encoding="utf-8")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["source_sha256"] = "0" * 64
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="source SHA256"):
        dialogue_pass.validate_dialogue_batch(manifest_path, raw_dir, tmp_path / "source-out")


@pytest.mark.parametrize(
    "case",
    ["manifest_schema", "payload_schema_hash", "payload_prompt_hash", "payload_contract", "first_pass_manifest"],
)
def test_validate_dialogue_batch_rejects_schema_payload_and_first_pass_manifest_tampering(
    tmp_path: Path, case: str
) -> None:
    manifest_path = _prepare(tmp_path)
    raw_dir = tmp_path / "raw"
    _write_empty_raw_batch(manifest_path, raw_dir)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    payload_path = manifest_path.parent / "payloads" / "0000.json"
    if case == "manifest_schema":
        manifest["output_contract_sha256"] = "4" * 64
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    elif case == "first_pass_manifest":
        first_pass = Path(manifest["first_pass_manifest_file"])
        first_pass.write_text(first_pass.read_text(encoding="utf-8") + " ", encoding="utf-8")
    else:
        payload = json.loads(payload_path.read_text(encoding="utf-8"))
        if case == "payload_schema_hash":
            payload["output_contract_sha256"] = "5" * 64
        elif case == "payload_prompt_hash":
            payload["prompt_sha256"] = "6" * 64
        else:
            payload["output_contract"]["title"] = "tampered"
        payload_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        manifest["candidates"][0]["payload_sha256"] = _sha256(payload_path)
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    destination = tmp_path / "published" / "knowledge-extraction" / "dialogue-pass" / "validated"
    with pytest.raises(ValueError, match="schema|contract|prompt|first-pass|payload"):
        dialogue_pass.validate_dialogue_batch(manifest_path, raw_dir, tmp_path / "published")
    assert not destination.exists()


def test_validate_dialogue_batch_rejects_tampered_source_segments_atomically(tmp_path: Path) -> None:
    segments = tmp_path / "source-segments.json"
    segments.write_bytes(SEGMENTS.read_bytes())
    manifest_path = _prepare(tmp_path, segments=segments)
    raw_dir = tmp_path / "raw"
    _write_empty_raw_batch(manifest_path, raw_dir)
    segments.write_text(segments.read_text(encoding="utf-8") + " ", encoding="utf-8")

    destination = tmp_path / "published" / "knowledge-extraction" / "dialogue-pass" / "validated"
    with pytest.raises(ValueError, match="source segments SHA256"):
        dialogue_pass.validate_dialogue_batch(manifest_path, raw_dir, tmp_path / "published")
    assert not destination.exists()


def test_validate_dialogue_batch_rejects_candidate_spans_that_differ_from_sidecar(tmp_path: Path) -> None:
    manifest_path = _prepare(tmp_path)
    raw_dir = tmp_path / "raw"
    _write_empty_raw_batch(manifest_path, raw_dir)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    payload_path = manifest_path.parent / "payloads" / "0006.json"
    payload = json.loads(payload_path.read_text(encoding="utf-8"))
    turn = payload["conversation"][1]
    quote = "return_delivered_order_items"
    start = turn["agent"].index(quote)
    turn["tool_result_spans"] = [{
        "quote": quote, "occurrence_index": 0, "marker_occurrence_index": 0,
        "start": start, "end": start + len(quote),
    }]
    payload_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    manifest["candidates"][6]["payload_sha256"] = _sha256(payload_path)
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    destination = tmp_path / "published" / "knowledge-extraction" / "dialogue-pass" / "validated"
    with pytest.raises(ValueError, match="source-segment|payload"):
        dialogue_pass.validate_dialogue_batch(manifest_path, raw_dir, tmp_path / "published")
    assert not destination.exists()


def test_validate_dialogue_batch_publishes_atomically_and_allows_sibling_raw(tmp_path: Path) -> None:
    manifest_path = _prepare(tmp_path)
    raw_dir = tmp_path / "dialogues" / "knowledge-extraction" / "dialogue-pass" / "raw"
    _write_empty_raw_batch(manifest_path, raw_dir)
    before = {
        path: _sha256(path)
        for path in Path(json.loads(manifest_path.read_text(encoding="utf-8"))["first_pass_manifest_file"]).parent.glob("*.json")
    }

    publication = dialogue_pass.validate_dialogue_batch(manifest_path, raw_dir, tmp_path / "dialogues")

    assert publication == tmp_path / "dialogues" / "knowledge-extraction" / "dialogue-pass" / "validated" / "manifest.json"
    aggregate = json.loads(publication.read_text(encoding="utf-8"))
    assert len(aggregate["candidates"]) == 10
    assert all(item["raw_sha256_before"] == item["raw_sha256_after"] for item in aggregate["candidates"])
    assert all(
        item["validated_sha256"] == _sha256(publication.parent / item["validated_file"])
        for item in aggregate["candidates"]
    )
    assert before == {path: _sha256(path) for path in before}


def test_validate_dialogue_batch_cleans_staging_on_injected_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest_path = _prepare(tmp_path)
    raw_dir = tmp_path / "raw"
    _write_empty_raw_batch(manifest_path, raw_dir)

    original = dialogue_pass._write_json

    def fail_manifest(path: Path, value: object) -> None:
        if path.name == "manifest.json":
            raise OSError("injected dialogue validation failure")
        original(path, value)

    monkeypatch.setattr(dialogue_pass, "_write_json", fail_manifest)
    with pytest.raises(OSError, match="injected dialogue"):
        dialogue_pass.validate_dialogue_batch(manifest_path, raw_dir, tmp_path / "published")
    root = tmp_path / "published" / "knowledge-extraction" / "dialogue-pass"
    assert not (root / "validated").exists()
    assert not list(root.glob("validated-*"))


def test_validate_dialogue_batch_rejects_overlapping_paths(tmp_path: Path) -> None:
    manifest_path = _prepare(tmp_path)
    raw_dir = tmp_path / "raw"
    _write_empty_raw_batch(manifest_path, raw_dir)
    with pytest.raises(ValueError, match="disjoint"):
        dialogue_pass.validate_dialogue_batch(manifest_path, raw_dir, raw_dir)
    with pytest.raises(ValueError, match="disjoint"):
        dialogue_pass.validate_dialogue_batch(manifest_path, raw_dir, raw_dir / "nested")


def test_cli_imports_and_dispatches_dialogue_commands(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[object, ...]] = []
    monkeypatch.setattr(
        "knowledge_pipeline.cli.prepare_dialogue_payloads",
        lambda source, manifest, output, prompt: calls.append((source, manifest, output, prompt)),
    )
    monkeypatch.setattr(
        "knowledge_pipeline.cli.validate_dialogue_batch",
        lambda manifest, raw, output: calls.append((manifest, raw, output)),
    )
    assert main([
        "prepare-dialogues", "--input", str(DATASET), "--turn-manifest", str(tmp_path / "turn-manifest.json"),
        "--output-dir", str(tmp_path), "--prompt", str(PROMPT),
    ]) == 0
    assert main([
        "validate-dialogues", "--manifest", str(tmp_path / "manifest.json"),
        "--raw-dir", str(tmp_path / "raw"), "--output-dir", str(tmp_path),
    ]) == 0
    assert len(calls) == 2
