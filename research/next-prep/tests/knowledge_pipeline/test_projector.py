from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pytest

from knowledge_pipeline.cli import build_parser
from knowledge_pipeline.projector import (
    project_final_knowledge,
    project_and_record,
    project_validated_manifests,
    record_projection_run,
    render_final_knowledge,
    write_projected_knowledge,
)


def _knowledge(
    knowledge_id: str,
    *,
    candidate_id: str = "CAND",
    turn_index: int = 0,
    subject: str = "user",
    predicate: str = "prefers",
    object_value: str = "coffee",
) -> dict[str, object]:
    return {
        "knowledge_id": knowledge_id,
        "candidate_id": candidate_id,
        "turn_index": turn_index,
        "statement": f"{subject} {predicate} {object_value}",
        "subject": subject,
        "predicate": predicate,
        "object": object_value,
        "qualifiers": {
            "modality": "asserted",
            "polarity": "positive",
            "temporal": [],
            "conditions": [],
            "scope": [],
        },
        "source_status": "user_reported",
        "derivation": "explicit",
        "evidence": [{"evidence_id": f"E_{knowledge_id}", "quote": object_value}],
        "inference_basis": None,
        "confidence": 0.9,
    }


def _operation(
    operation_id: str,
    operation: str,
    *,
    targets: list[str],
    replacement: str | None = None,
) -> dict[str, object]:
    return {
        "operation_id": operation_id,
        "candidate_id": "CAND",
        "operation": operation,
        "targets": targets,
        "replacement": replacement,
        "reason": "dialogue evidence",
        "evidence": [{"evidence_id": f"E_{operation_id}", "quote": "evidence"}],
        "confidence": 0.95,
    }


def test_corrected_record_is_retained_but_not_active() -> None:
    old = _knowledge("K_old")
    new = _knowledge("D_new", turn_index=1, object_value="tea")
    view = project_final_knowledge(
        [old],
        [{
            "candidate_id": "CAND",
            "new_knowledge": [new],
            "operations": [_operation("R_001", "correct", targets=["K_old"], replacement="D_new")],
        }],
    )

    assert view.by_id["K_old"].status == "corrected"
    assert view.by_id["K_old"].replacement_id == "D_new"
    assert view.by_id["D_new"].status == "active"
    assert view.by_id["D_new"].replaces == ("K_old",)
    assert "K_old" not in view.active_ids


def test_superseded_record_is_retained_and_replacement_remains_active() -> None:
    old = _knowledge("K_old")
    replacement = _knowledge("K_current", turn_index=1, object_value="tea")
    view = project_final_knowledge(
        [old, replacement],
        [{
            "candidate_id": "CAND",
            "new_knowledge": [],
            "operations": [_operation("R_001", "supersede", targets=["K_old"], replacement="K_current")],
        }],
    )

    assert view.by_id["K_old"].status == "superseded"
    assert view.by_id["K_old"].replacement_id == "K_current"
    assert view.by_id["K_current"].status == "active"
    assert view.by_id["K_current"].supersedes == ("K_old",)


def test_conflicting_records_both_remain_active() -> None:
    first = _knowledge("K_a", object_value="coffee")
    second = _knowledge("K_b", object_value="tea")
    view = project_final_knowledge(
        [first, second],
        [{
            "candidate_id": "CAND",
            "new_knowledge": [],
            "operations": [_operation("R_001", "conflict", targets=["K_a", "K_b"])],
        }],
    )

    assert {"K_a", "K_b"} <= set(view.active_ids)
    assert view.by_id["K_a"].status == "active_conflict"
    assert view.by_id["K_a"].conflicts_with == ("K_b",)
    assert view.by_id["K_b"].conflicts_with == ("K_a",)


def test_confirmed_record_remains_active_and_collects_operation_id() -> None:
    view = project_final_knowledge(
        [_knowledge("K_a")],
        [{
            "candidate_id": "CAND",
            "new_knowledge": [],
            "operations": [_operation("R_001", "confirm", targets=["K_a"])],
        }],
    )

    assert view.by_id["K_a"].status == "active"
    assert view.by_id["K_a"].confirmed_by == ("R_001",)


def test_equivalent_records_are_linked_without_deduplication() -> None:
    first = _knowledge("K_a", turn_index=0)
    second = _knowledge("K_b", turn_index=1)
    view = project_final_knowledge([first, second], [])

    assert len(view.records) == 2
    assert view.by_id["K_a"].equivalence_group is not None
    assert view.by_id["K_a"].equivalence_group == view.by_id["K_b"].equivalence_group
    assert view.by_id["K_a"].evidence != view.by_id["K_b"].evidence


def test_projection_is_stable_and_does_not_mutate_inputs() -> None:
    knowledge = [_knowledge("K_b", candidate_id="B"), _knowledge("K_a", candidate_id="A")]
    dialogue: list[dict[str, object]] = []
    original_knowledge = copy.deepcopy(knowledge)
    original_dialogue = copy.deepcopy(dialogue)

    first = render_final_knowledge(project_final_knowledge(knowledge, dialogue))
    second = render_final_knowledge(project_final_knowledge(knowledge, dialogue))

    assert first == second
    assert first.endswith(b"\n")
    assert json.loads(first)["active_ids"] == ["K_a", "K_b"]
    assert knowledge == original_knowledge
    assert dialogue == original_dialogue


def test_projection_rejects_unknown_operation_references() -> None:
    with pytest.raises(ValueError, match="unknown target"):
        project_final_knowledge(
            [_knowledge("K_a")],
            [{
                "candidate_id": "CAND",
                "new_knowledge": [],
                "operations": [_operation("R_001", "confirm", targets=["K_missing"])],
            }],
        )


def test_add_operation_keeps_new_knowledge_active_and_links_operation() -> None:
    new = _knowledge("D_added", turn_index=1, object_value="tea")
    view = project_final_knowledge(
        [],
        [{
            "candidate_id": "CAND",
            "new_knowledge": [new],
            "operations": [_operation("R_001", "add", targets=[], replacement="D_added")],
        }],
    )

    assert view.by_id["D_added"].status == "active"
    assert view.by_id["D_added"].added_by == ("R_001",)


def _write_json(path: Path, value: object) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    path.write_text(content, encoding="utf-8")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _validated_fixture(tmp_path: Path) -> tuple[Path, Path]:
    turn_dir = tmp_path / "turn-pass" / "validated"
    dialogue_dir = tmp_path / "dialogue-pass" / "validated"
    turn_file = turn_dir / "0000-0000.json"
    old = _knowledge("K_old")
    _write_json(turn_file, {"candidate_id": "CAND", "turn_index": 0, "context_completions": [], "knowledge": [old]})
    turn_manifest = turn_dir / "manifest.json"
    turn_manifest_hash = _write_json(turn_manifest, {
        "prompt_version": "turn-v1",
        "prompt_sha256": "1" * 64,
        "output_contract_sha256": "2" * 64,
        "source_segments_file": "source-segments.json",
        "source_segments_sha256": "3" * 64,
        "turns": [{
            "validated_file": turn_file.name,
            "candidate_id": "CAND",
            "candidate_index": 0,
            "turn_index": 0,
            "raw_sha256_before": "4" * 64,
            "raw_sha256_after": "4" * 64,
        }],
    })
    new = _knowledge("D_new", turn_index=1, object_value="tea")
    dialogue_file = dialogue_dir / "0000.json"
    dialogue_file_hash = _write_json(dialogue_file, {
        "candidate_id": "CAND",
        "new_knowledge": [new],
        "operations": [_operation("R_001", "correct", targets=["K_old"], replacement="D_new")],
    })
    dialogue_manifest = dialogue_dir / "manifest.json"
    _write_json(dialogue_manifest, {
        "prompt_version": "dialogue-v1",
        "prompt_sha256": "5" * 64,
        "output_contract_sha256": "6" * 64,
        "source_sha256": "7" * 64,
        "first_pass_manifest_sha256": turn_manifest_hash,
        "source_segments_file": "source-segments.json",
        "source_segments_sha256": "3" * 64,
        "candidates": [{
            "candidate_id": "CAND",
            "candidate_index": 0,
            "canonical_filename": dialogue_file.name,
            "validated_file": dialogue_file.name,
            "validated_sha256": dialogue_file_hash,
            "first_pass_files": [{
                "canonical_filename": turn_file.name,
                "sha256": hashlib.sha256(turn_file.read_bytes()).hexdigest(),
            }],
            "raw_sha256_before": "8" * 64,
            "raw_sha256_after": "8" * 64,
        }],
    })
    return turn_manifest, dialogue_manifest


def test_project_validated_manifests_checks_hash_closure(tmp_path: Path) -> None:
    turn_manifest, dialogue_manifest = _validated_fixture(tmp_path)

    view = project_validated_manifests(turn_manifest, dialogue_manifest)

    assert view.by_id["K_old"].status == "corrected"
    assert view.by_id["D_new"].status == "active"
    assert view.provenance["turn_manifest_sha256"] == hashlib.sha256(turn_manifest.read_bytes()).hexdigest()


def test_project_validated_manifests_rejects_tampered_turn_file(tmp_path: Path) -> None:
    turn_manifest, dialogue_manifest = _validated_fixture(tmp_path)
    turn_file = turn_manifest.parent / "0000-0000.json"
    turn_file.write_text(turn_file.read_text(encoding="utf-8") + " ", encoding="utf-8")

    with pytest.raises(ValueError, match="first-pass file hash"):
        project_validated_manifests(turn_manifest, dialogue_manifest)


def test_project_validated_manifests_rejects_tampered_dialogue_file(tmp_path: Path) -> None:
    turn_manifest, dialogue_manifest = _validated_fixture(tmp_path)
    dialogue_file = dialogue_manifest.parent / "0000.json"
    value = json.loads(dialogue_file.read_text(encoding="utf-8"))
    value["operations"][0]["reason"] = "tampered but same candidate"
    dialogue_file.write_text(json.dumps(value), encoding="utf-8")

    with pytest.raises(ValueError, match="dialogue validated file hash"):
        project_validated_manifests(turn_manifest, dialogue_manifest)


def test_write_projected_knowledge_is_byte_deterministic(tmp_path: Path) -> None:
    turn_manifest, dialogue_manifest = _validated_fixture(tmp_path)
    output = tmp_path / "final-knowledge.json"

    first = write_projected_knowledge(turn_manifest, dialogue_manifest, output)
    first_bytes = output.read_bytes()
    second = write_projected_knowledge(turn_manifest, dialogue_manifest, output)

    assert output.read_bytes() == first_bytes
    assert first.sha256 == second.sha256 == hashlib.sha256(first_bytes).hexdigest()
    assert first.active_count == 1


def test_cli_registers_project_command_with_workspace_defaults() -> None:
    args = build_parser().parse_args(["project"])

    assert args.turn_manifest == Path("knowledge-extraction/turn-pass/validated/manifest.json")
    assert args.dialogue_manifest == Path("knowledge-extraction/dialogue-pass/validated/manifest.json")
    assert args.output == Path("knowledge-extraction/final-knowledge.json")
    assert args.run == Path("knowledge-extraction/run.json")


def test_record_projection_run_is_atomic_and_preserves_existing_sections(tmp_path: Path) -> None:
    turn_manifest, dialogue_manifest = _validated_fixture(tmp_path)
    output = tmp_path / "final-knowledge.json"
    artifact = write_projected_knowledge(turn_manifest, dialogue_manifest, output)
    run_path = tmp_path / "run.json"
    provenance = artifact.view.provenance
    assert provenance is not None
    existing_turn = {
        "status": "validated",
        "validated_manifest": {"sha256": provenance["turn_manifest_sha256"]},
    }
    _write_json(run_path, {
        "schema_version": "run-v1",
        "source_segments": {"sha256": provenance["source_segments_sha256"]},
        "turn_pass": existing_turn,
        "dialogue_pass": {"status": "validated", "validated_manifest": {"sha256": provenance["dialogue_manifest_sha256"]}},
    })

    record_projection_run(run_path, artifact)
    value = json.loads(run_path.read_text(encoding="utf-8"))

    assert value["turn_pass"] == existing_turn
    assert value["projection"]["status"] == "projected"
    assert value["projection"]["output_sha256"] == artifact.sha256
    assert value["projection"]["active_count"] == artifact.active_count
    assert not run_path.with_name("run.json.new").exists()


def test_record_projection_run_rejects_stale_manifest_metadata(tmp_path: Path) -> None:
    turn_manifest, dialogue_manifest = _validated_fixture(tmp_path)
    artifact = write_projected_knowledge(turn_manifest, dialogue_manifest, tmp_path / "final.json")
    run_path = tmp_path / "run.json"
    _write_json(run_path, {
        "source_segments": {"sha256": "0" * 64},
        "turn_pass": {"validated_manifest": {"sha256": "0" * 64}},
        "dialogue_pass": {"validated_manifest": {"sha256": "0" * 64}},
    })

    with pytest.raises(ValueError, match="run metadata"):
        record_projection_run(run_path, artifact)


def test_project_and_record_rolls_back_output_when_run_publish_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    turn_manifest, dialogue_manifest = _validated_fixture(tmp_path)
    probe = write_projected_knowledge(turn_manifest, dialogue_manifest, tmp_path / "probe.json")
    provenance = probe.view.provenance
    assert provenance is not None
    output = tmp_path / "final.json"
    output.write_bytes(b"old-output\n")
    run_path = tmp_path / "run.json"
    _write_json(run_path, {
        "source_segments": {"sha256": provenance["source_segments_sha256"]},
        "turn_pass": {"validated_manifest": {"sha256": provenance["turn_manifest_sha256"]}},
        "dialogue_pass": {"validated_manifest": {"sha256": provenance["dialogue_manifest_sha256"]}},
    })
    import knowledge_pipeline.projector as projector

    original_replace = projector.os.replace

    def fail_run_publish(source: object, destination: object) -> None:
        if Path(destination) == run_path.resolve():
            raise OSError("injected run publication failure")
        original_replace(source, destination)

    monkeypatch.setattr(projector.os, "replace", fail_run_publish)
    with pytest.raises(OSError, match="injected run"):
        project_and_record(turn_manifest, dialogue_manifest, output, run_path)

    assert output.read_bytes() == b"old-output\n"
    assert not output.with_name("final.json.new").exists()
    assert not output.with_name("final.json.backup").exists()
    assert not run_path.with_name("run.json.new").exists()
