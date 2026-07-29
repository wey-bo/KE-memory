from __future__ import annotations

import hashlib
import json
import copy
from pathlib import Path
from threading import Lock

import pytest

from tools.ontology_memory_experiment.runner import (
    ExperimentRunConfig,
    run_experiment,
    verify_run,
)
import tools.ontology_memory_experiment.runner as runner_module


ARMS = ("B0", "B1", "B2", "O-", "O+", "O+E")
TRACKS = ("oracle", "automatic")


def _source() -> dict[str, object]:
    return {
        "schema_version": "ontology-memory-source-v1",
        "scenarios": [
            {
                "scenario_id": f"OME-S{index:03d}",
                "language": "en",
                "turns": [
                    {
                        "turn_id": f"OME-S{index:03d}-T{turn:02d}",
                        "speaker": "user" if turn % 2 else "agent",
                        "text": f"Turn {turn} for scenario {index}.",
                    }
                    for turn in range(1, 5)
                ],
                "question": f"What is the answer for scenario {index}?",
                "candidate_answer_budget": 51,
            }
            for index in (1, 2)
        ],
    }


def _gold() -> dict[str, object]:
    return {
        "schema_version": "ontology-memory-gold-v1",
        "status": "frozen",
        "scenarios": [
            {
                "scenario_id": f"OME-S{index:03d}",
                "family": "roles_polarity_modality_quantity",
                "origin": "neutral",
                "primary_system": None,
                "split": "dev",
                "answer": {"kind": "value", "values": [f"answer-{index}"]},
                "required_evidence_turn_ids": [f"OME-S{index:03d}-T03"],
                "hard_negative_turn_ids": [f"OME-S{index:03d}-T02"],
                "required_primitives": ["role"],
                "critical_constraints": ["agent_role"],
                "architecture_claim_ids": [],
                "proposed_ontology_remedy": "typed roles",
                "falsifier": "ranking matches execution",
            }
            for index in (1, 2)
        ],
    }


def _distractors() -> dict[str, object]:
    records = []
    for scenario in (1, 2):
        for scale in (50, 500):
            for index in range(scale):
                records.append(
                    {
                        "scenario_id": f"OME-S{scenario:03d}",
                        "scale": scale,
                        "record_id": f"OME-S{scenario:03d}-D{scale}-{index:03d}",
                        "text": f"Distractor {index} for scenario {scenario}.",
                        "entities": [f"distractor-{index}"],
                        "predicate": "distractor",
                        "roles": {},
                    }
                )
    return {
        "schema_version": "ontology-memory-distractors-v1",
        "records": records,
    }


def _oracle_representations() -> dict[str, object]:
    return {
        "schema_version": "ontology-memory-oracle-representations-v1",
        "scenarios": [
            {
                "scenario_id": f"OME-S{index:03d}",
                "records": [
                    {
                        "record_id": f"OME-S{index:03d}-R01",
                        "source_turn_ids": [f"OME-S{index:03d}-T03"],
                        "surface_text": f"The answer is answer-{index}.",
                        "entities": [f"answer-{index}"],
                        "predicate": "answer",
                        "roles": {"value": f"answer-{index}"},
                        "polarity": "positive",
                        "modality": "asserted",
                        "quantity": None,
                        "valid_time": None,
                        "transaction_time": None,
                        "provenance_status": "user_reported",
                        "conflict_group": None,
                        "supersedes": [],
                        "relations": [],
                    }
                ],
                "ablated_records": [
                    {
                        "record_id": f"OME-S{index:03d}-R01",
                        "source_turn_ids": [f"OME-S{index:03d}-T03"],
                        "surface_text": f"The answer is answer-{index}.",
                        "entities": [f"answer-{index}"],
                        "predicate": "answer",
                        "roles": {},
                        "polarity": "positive",
                        "modality": "asserted",
                        "quantity": None,
                        "valid_time": None,
                        "transaction_time": None,
                        "provenance_status": "user_reported",
                        "conflict_group": None,
                        "supersedes": [],
                        "relations": [],
                    }
                ],
            }
            for index in (1, 2)
        ],
    }


def _oracle_query_plans() -> dict[str, object]:
    return {
        "schema_version": "ontology-memory-oracle-query-plans-v1",
        "scenarios": [
            {
                "scenario_id": f"OME-S{index:03d}",
                "query_plan": {
                    "entity_candidates": [],
                    "predicate": "answer",
                    "role_constraints": {},
                    "polarity": "positive",
                    "modality": "asserted",
                    "quantity": None,
                    "time_filter": None,
                    "status_filter": None,
                    "provenance_filter": "user_reported",
                    "conjunction_groups": [],
                    "traversal_steps": [],
                    "required_answer_slot": "value",
                    "declared_unresolved_slots": [],
                },
            }
            for index in (1, 2)
        ],
    }


class FakeEncoder:
    model_metadata = {
        "provider": "fixture",
        "model_id": "fixture-encoder",
        "revision": "fixture-revision",
        "dimensions": 3,
    }

    def encode(self, texts):
        return [[1.0, 0.0, 0.0] for _ in texts]


def test_runner_executes_each_base_scenario_track_arm_and_scale_once(tmp_path: Path) -> None:
    calls: list[tuple[str, str, int]] = []
    lock = Lock()

    def execute(*, arm, scenario, records, query_plan, distractors, encoder):
        assert records
        assert set(query_plan).isdisjoint({"answer", "required_evidence_turn_ids"})
        with lock:
            calls.append((scenario["scenario_id"], arm, len(distractors)))
        return {
            "selected_evidence_turn_ids": [scenario["turns"][2]["turn_id"]],
            "ranked_evidence": [],
            "predicted_answer": "fixture",
            "abstained": False,
            "constraint_checks": [],
            "symbolic_trace": [],
            "fallback": {"triggered": False, "reason": None, "rejected_candidates": []},
            "latency_ms": 1.0,
            "error": None,
        }

    output = tmp_path / "run"
    summary = run_experiment(
        source_document=_source(),
        gold_document=_gold(),
        distractor_document=_distractors(),
        oracle_representation_document=_oracle_representations(),
        oracle_query_plan_document=_oracle_query_plans(),
        output_dir=output,
        encoder=FakeEncoder(),
        config=ExperimentRunConfig(run_id="run-20260725T120000Z", workers=4),
        execute=execute,
    )

    assert summary.result_count == 2 * len(TRACKS) * len(ARMS) * 3
    assert len(calls) == summary.result_count
    assert {item[2] for item in calls} == {0, 50, 500}
    assert (output / "manifest.json").is_file()
    assert (output / "results.jsonl").is_file()


def test_concurrent_run_output_is_deterministically_sorted(tmp_path: Path) -> None:
    def execute(*, arm, scenario, records, query_plan, distractors, encoder):
        return {
            "selected_evidence_turn_ids": [],
            "ranked_evidence": [],
            "predicted_answer": None,
            "abstained": True,
            "constraint_checks": [],
            "symbolic_trace": [],
            "fallback": {"triggered": False, "reason": None, "rejected_candidates": []},
            "latency_ms": 0.0,
            "error": None,
        }

    output = tmp_path / "run"
    run_experiment(
        source_document=_source(),
        gold_document=_gold(),
        distractor_document=_distractors(),
        oracle_representation_document=_oracle_representations(),
        oracle_query_plan_document=_oracle_query_plans(),
        output_dir=output,
        encoder=FakeEncoder(),
        config=ExperimentRunConfig(run_id="run-20260725T120001Z", workers=4),
        execute=execute,
    )
    rows = [json.loads(line) for line in (output / "results.jsonl").read_text(encoding="utf-8").splitlines()]
    keys = [
        (row["scenario_id"], row["track"], row["arm"], row["distractor_scale"])
        for row in rows
    ]
    assert keys == sorted(keys)


def test_run_is_immutable_and_verifier_detects_tampering(tmp_path: Path) -> None:
    def execute(**kwargs):
        return {
            "selected_evidence_turn_ids": [],
            "ranked_evidence": [],
            "predicted_answer": None,
            "abstained": True,
            "constraint_checks": [],
            "symbolic_trace": [],
            "fallback": {"triggered": False, "reason": None, "rejected_candidates": []},
            "latency_ms": 0.0,
            "error": None,
        }

    output = tmp_path / "run"
    arguments = dict(
        source_document=_source(),
        gold_document=_gold(),
        distractor_document=_distractors(),
        oracle_representation_document=_oracle_representations(),
        oracle_query_plan_document=_oracle_query_plans(),
        output_dir=output,
        encoder=FakeEncoder(),
        config=ExperimentRunConfig(run_id="run-20260725T120002Z", workers=2),
        execute=execute,
    )
    run_experiment(**arguments)
    with pytest.raises(ValueError, match="refusing to overwrite"):
        run_experiment(**arguments)

    verification = verify_run(output)
    assert verification["status"] == "valid"
    source_snapshot = output / "inputs" / "source.json"
    original_source = source_snapshot.read_bytes()
    source_snapshot.write_bytes(original_source + b" ")
    with pytest.raises(ValueError, match="source_sha256"):
        verify_run(output)
    source_snapshot.write_bytes(original_source)
    results = output / "results.jsonl"
    results.write_text(results.read_text(encoding="utf-8") + "{}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="sha256"):
        verify_run(output)


def test_manifest_binds_source_gold_distractors_and_model(tmp_path: Path) -> None:
    def execute(**kwargs):
        return {
            "selected_evidence_turn_ids": [],
            "ranked_evidence": [],
            "predicted_answer": None,
            "abstained": True,
            "constraint_checks": [],
            "symbolic_trace": [],
            "fallback": {"triggered": False, "reason": None, "rejected_candidates": []},
            "latency_ms": 0.0,
            "error": None,
        }

    output = tmp_path / "run"
    run_experiment(
        source_document=_source(),
        gold_document=_gold(),
        distractor_document=_distractors(),
        oracle_representation_document=_oracle_representations(),
        oracle_query_plan_document=_oracle_query_plans(),
        output_dir=output,
        encoder=FakeEncoder(),
        config=ExperimentRunConfig(run_id="run-20260725T120003Z", workers=1),
        execute=execute,
    )
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["model"] == FakeEncoder.model_metadata
    for name in (
        "source_sha256",
        "gold_sha256",
        "distractors_sha256",
        "oracle_representations_sha256",
        "oracle_query_plans_sha256",
        "results_sha256",
    ):
        assert len(manifest[name]) == 64
        int(manifest[name], 16)
    assert manifest["results_sha256"] == hashlib.sha256((output / "results.jsonl").read_bytes()).hexdigest()
    assert set(path.name for path in (output / "inputs").iterdir()) == {
        "source.json",
        "gold.json",
        "distractors.json",
        "oracle-representations.json",
        "oracle-query-plans.json",
    }


def test_runner_measures_executor_wall_clock_and_preserves_reported_latency(tmp_path: Path) -> None:
    ticks = iter((10.0, 10.125, 20.0, 20.5))

    def execute(**kwargs):
        return {
            "selected_evidence_turn_ids": [],
            "ranked_evidence": [],
            "predicted_answer": None,
            "abstained": True,
            "constraint_checks": [],
            "symbolic_trace": [],
            "fallback": {"triggered": False, "reason": None, "rejected_candidates": []},
            "latency_ms": 999_999.0,
            "error": None,
        }

    output = tmp_path / "run"
    run_experiment(
        source_document=_source(),
        gold_document=_gold(),
        distractor_document=_distractors(),
        oracle_representation_document=_oracle_representations(),
        oracle_query_plan_document=_oracle_query_plans(),
        output_dir=output,
        encoder=FakeEncoder(),
        config=ExperimentRunConfig(
            run_id="run-20260725T120004Z",
            workers=1,
            arms=("B0",),
            tracks=("oracle",),
            scales=(0,),
        ),
        execute=execute,
        clock=lambda: next(ticks),
    )

    rows = [json.loads(line) for line in (output / "results.jsonl").read_text(encoding="utf-8").splitlines()]
    assert [row["latency_ms"] for row in rows] == pytest.approx([125.0, 500.0])
    assert [row["executor_latency_ms"] for row in rows] == [999_999.0, 999_999.0]


def test_manifest_captures_encoder_cache_diagnostics_after_execution(tmp_path: Path) -> None:
    class RuntimeStatsEncoder(FakeEncoder):
        def __init__(self) -> None:
            self.model_metadata = dict(FakeEncoder.model_metadata)
            self.cache_hits = 0
            self.cache_misses = 0
            self.encoded_text_count = 0

        def encode(self, texts):
            self.cache_hits += 2
            self.cache_misses += 1
            self.encoded_text_count += len(texts)
            return super().encode(texts)

    encoder = RuntimeStatsEncoder()

    def execute(*, encoder, **kwargs):
        encoder.encode(("cached", "new"))
        return {
            "selected_evidence_turn_ids": [],
            "ranked_evidence": [],
            "predicted_answer": None,
            "abstained": True,
            "constraint_checks": [],
            "symbolic_trace": [],
            "fallback": {"triggered": False, "reason": None, "rejected_candidates": []},
            "latency_ms": None,
            "error": None,
        }

    output = tmp_path / "run"
    run_experiment(
        source_document=_source(),
        gold_document=_gold(),
        distractor_document=_distractors(),
        oracle_representation_document=_oracle_representations(),
        oracle_query_plan_document=_oracle_query_plans(),
        output_dir=output,
        encoder=encoder,
        config=ExperimentRunConfig(
            run_id="run-20260725T120005Z",
            workers=1,
            arms=("O+E",),
            tracks=("oracle",),
            scales=(0,),
        ),
        execute=execute,
    )

    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["model"]["cache_hits"] == 4
    assert manifest["model"]["cache_misses"] == 2
    assert manifest["model"]["encoded_text_count"] == 4


def _single_scenario_documents() -> tuple[dict[str, object], ...]:
    source = _source()
    gold = _gold()
    distractors = _distractors()
    representations = _oracle_representations()
    query_plans = _oracle_query_plans()
    selected_id = "OME-S001"
    source["scenarios"] = [source["scenarios"][0]]
    gold["scenarios"] = [gold["scenarios"][0]]
    representations["scenarios"] = [representations["scenarios"][0]]
    query_plans["scenarios"] = [query_plans["scenarios"][0]]
    distractors["records"] = [
        item for item in distractors["records"] if item["scenario_id"] == selected_id
    ]
    return source, gold, distractors, representations, query_plans


def test_automatic_phase_latency_includes_representation_and_query_compilation(tmp_path: Path) -> None:
    source, gold, distractors, representations, query_plans = _single_scenario_documents()
    ticks = iter((0.0, 0.1, 0.3, 0.8, 1.0))

    def execute(**kwargs):
        return {
            "selected_evidence_turn_ids": [],
            "ranked_evidence": [],
            "predicted_answer": None,
            "abstained": True,
            "constraint_checks": {},
            "symbolic_trace": [],
            "fallback": {"triggered": False, "reason": None, "rejected_candidates": []},
            "latency_ms": 1.0,
            "error": None,
        }

    output = tmp_path / "run"
    run_experiment(
        source_document=source,
        gold_document=gold,
        distractor_document=distractors,
        oracle_representation_document=representations,
        oracle_query_plan_document=query_plans,
        output_dir=output,
        encoder=FakeEncoder(),
        config=ExperimentRunConfig(
            run_id="run-20260725T120006Z",
            workers=1,
            arms=("B0",),
            tracks=("automatic",),
            scales=(0,),
        ),
        execute=execute,
        clock=lambda: next(ticks),
    )
    row = json.loads((output / "results.jsonl").read_text(encoding="utf-8"))
    assert row["representation_latency_ms"] == pytest.approx(100.0)
    assert row["query_compile_latency_ms"] == pytest.approx(200.0)


def test_b0_receives_raw_turn_records_in_both_tracks(tmp_path: Path) -> None:
    source, gold, distractors, representations, query_plans = _single_scenario_documents()
    seen: dict[tuple[str, str], list[str]] = {}

    def execute(*, track, arm, records, **kwargs):
        seen[(track, arm)] = [str(record["record_id"]) for record in records]
        return {
            "selected_evidence_turn_ids": [],
            "ranked_evidence": [],
            "predicted_answer": None,
            "abstained": True,
            "constraint_checks": {},
            "symbolic_trace": [],
            "fallback": {"triggered": False, "reason": None, "rejected_candidates": []},
            "latency_ms": 0.0,
            "error": None,
        }

    run_experiment(
        source_document=source,
        gold_document=gold,
        distractor_document=distractors,
        oracle_representation_document=representations,
        oracle_query_plan_document=query_plans,
        output_dir=tmp_path / "run",
        encoder=FakeEncoder(),
        config=ExperimentRunConfig(
            run_id="run-20260725T120007Z",
            workers=1,
            arms=("B0", "B1"),
            tracks=TRACKS,
            scales=(0,),
        ),
        execute=execute,
    )
    expected = [turn["turn_id"] for turn in source["scenarios"][0]["turns"]]
    assert seen[("oracle", "B0")] == expected
    assert seen[("automatic", "B0")] == expected


def test_source_budget_must_cover_required_evidence_tokens(tmp_path: Path) -> None:
    source, gold, distractors, representations, query_plans = _single_scenario_documents()
    source["scenarios"][0]["candidate_answer_budget"] = 1

    def execute(**kwargs):
        raise AssertionError("execution must not start with an invalid source budget")

    with pytest.raises(ValueError, match="budget.*required evidence"):
        run_experiment(
            source_document=source,
            gold_document=gold,
            distractor_document=distractors,
            oracle_representation_document=representations,
            oracle_query_plan_document=query_plans,
            output_dir=tmp_path / "run",
            encoder=FakeEncoder(),
            config=ExperimentRunConfig(
                run_id="run-20260725T120008Z",
                workers=1,
                arms=("O+",),
                tracks=("oracle",),
                scales=(0,),
            ),
            execute=execute,
        )


def test_all_arms_receive_the_same_evidence_token_budget(tmp_path: Path) -> None:
    source, gold, distractors, representations, query_plans = _single_scenario_documents()
    budgets: list[int] = []

    def execute(*, evidence_token_budget, **kwargs):
        budgets.append(evidence_token_budget)
        return {
            "selected_evidence_turn_ids": [],
            "ranked_evidence": [],
            "predicted_answer": None,
            "abstained": True,
            "constraint_checks": {},
            "symbolic_trace": [],
            "fallback": {"triggered": False, "reason": None, "rejected_candidates": []},
            "latency_ms": 0.0,
            "error": None,
        }

    run_experiment(
        source_document=source,
        gold_document=gold,
        distractor_document=distractors,
        oracle_representation_document=representations,
        oracle_query_plan_document=query_plans,
        output_dir=tmp_path / "run",
        encoder=FakeEncoder(),
        config=ExperimentRunConfig(
            run_id="run-20260725T120011Z",
            workers=1,
            arms=ARMS,
            tracks=TRACKS,
            scales=(0,),
        ),
        execute=execute,
    )
    assert len(budgets) == len(ARMS) * len(TRACKS)
    assert set(budgets) == {51}


def test_symbolic_arm_uses_typed_distractors_from_representation_fixture(tmp_path: Path) -> None:
    source, gold, distractors, representations, query_plans = _single_scenario_documents()
    raw_records = []
    typed_records = []
    for record in distractors["records"]:
        item = dict(record)
        item.pop("entities", None)
        item.pop("predicate", None)
        item.pop("roles", None)
        raw_records.append(item)
        typed_records.append({
            "record_id": item["record_id"],
            "entities": ["typed-distractor"],
            "predicate": "distractor",
            "roles": {"kind": "typed"},
        })
    distractors["records"] = raw_records
    representations["scenarios"][0]["oracle_distractor_records"] = typed_records
    seen: list[dict[str, object]] = []

    def execute(*, distractors, **kwargs):
        seen.extend(distractors)
        return {
            "selected_evidence_turn_ids": [],
            "ranked_evidence": [],
            "predicted_answer": None,
            "abstained": True,
            "constraint_checks": {},
            "symbolic_trace": [],
            "fallback": {"triggered": False, "reason": None, "rejected_candidates": []},
            "latency_ms": 0.0,
            "error": None,
        }

    run_experiment(
        source_document=source,
        gold_document=gold,
        distractor_document=distractors,
        oracle_representation_document=representations,
        oracle_query_plan_document=query_plans,
        output_dir=tmp_path / "run",
        encoder=FakeEncoder(),
        config=ExperimentRunConfig(
            run_id="run-20260725T120012Z",
            workers=1,
            arms=("O+",),
            tracks=("oracle",),
            scales=(50,),
        ),
        execute=execute,
    )
    assert len(seen) == 50
    assert all(item["predicate"] == "distractor" for item in seen)
    assert all(item["roles"] == {"kind": "typed"} for item in seen)


def test_nested_typed_distractors_are_selected_by_scale_and_record_id(tmp_path: Path) -> None:
    source, gold, distractors, representations, query_plans = _single_scenario_documents()
    raw_records = []
    typed_by_scale: dict[str, list[dict[str, object]]] = {"50": [], "500": []}
    for item in distractors["records"]:
        raw = {key: value for key, value in item.items() if key not in {"entities", "predicate", "roles"}}
        raw_records.append(raw)
        scale = str(item["scale"])
        typed_by_scale[scale].append({
            "record_id": item["record_id"],
            "entities": ["nested-typed"],
            "predicate": "distractor",
            "roles": {"kind": scale},
        })
    distractors["records"] = raw_records
    representations["scenarios"][0]["distractor_records"] = typed_by_scale
    seen: list[dict[str, object]] = []

    def execute(*, distractors, **kwargs):
        seen.extend(distractors)
        return {
            "selected_evidence_turn_ids": [],
            "ranked_evidence": [],
            "predicted_answer": None,
            "abstained": True,
            "constraint_checks": {},
            "symbolic_trace": [],
            "fallback": {"triggered": False, "reason": None, "rejected_candidates": []},
            "latency_ms": 0.0,
            "error": None,
        }

    run_experiment(
        source_document=source,
        gold_document=gold,
        distractor_document=distractors,
        oracle_representation_document=representations,
        oracle_query_plan_document=query_plans,
        output_dir=tmp_path / "run",
        encoder=FakeEncoder(),
        config=ExperimentRunConfig(
            run_id="run-20260725T120013Z",
            workers=1,
            arms=("O+",),
            tracks=("oracle",),
            scales=(50,),
        ),
        execute=execute,
    )
    assert len(seen) == 50
    assert {item["roles"]["kind"] for item in seen} == {"50"}


def test_automatic_symbolic_arm_builds_typed_distractors_from_selected_text(
    monkeypatch, tmp_path: Path
) -> None:
    source, gold, distractors, representations, query_plans = _single_scenario_documents()
    for item in distractors["records"]:
        item.pop("entities", None)
        item.pop("predicate", None)
        item.pop("roles", None)
    built: list[dict[str, object]] = []

    def build_selected(selected):
        built.extend(selected)
        return [
            {
                "record_id": item["record_id"],
                "source_turn_ids": [item["record_id"]],
                "surface_text": item["text"],
                "entities": ["automatic-typed"],
                "predicate": "distractor",
                "roles": {},
                "relations": [],
            }
            for item in selected
        ]

    monkeypatch.setattr(runner_module, "build_distractor_representations", build_selected, raising=False)
    seen: list[dict[str, object]] = []

    def execute(*, distractors, **kwargs):
        seen.extend(distractors)
        return {
            "selected_evidence_turn_ids": [],
            "ranked_evidence": [],
            "predicted_answer": None,
            "abstained": True,
            "constraint_checks": {},
            "symbolic_trace": [],
            "fallback": {"triggered": False, "reason": None, "rejected_candidates": []},
            "latency_ms": 0.0,
            "error": None,
        }

    run_experiment(
        source_document=source,
        gold_document=gold,
        distractor_document=distractors,
        oracle_representation_document=representations,
        oracle_query_plan_document=query_plans,
        output_dir=tmp_path / "run",
        encoder=FakeEncoder(),
        config=ExperimentRunConfig(
            run_id="run-20260725T120014Z",
            workers=1,
            arms=("O+",),
            tracks=("automatic",),
            scales=(50,),
        ),
        execute=execute,
    )
    assert len(built) == 50
    assert len(seen) == 50
    assert all(item["predicate"] == "distractor" for item in seen)


def test_distractor_text_is_counted_when_selected_as_evidence(tmp_path: Path) -> None:
    source, gold, distractors, representations, query_plans = _single_scenario_documents()
    selected_id = distractors["records"][0]["record_id"]

    def execute(**kwargs):
        return {
            "selected_evidence_turn_ids": [selected_id],
            "ranked_evidence": [],
            "predicted_answer": None,
            "abstained": True,
            "constraint_checks": {},
            "symbolic_trace": [],
            "fallback": {"triggered": False, "reason": None, "rejected_candidates": []},
            "latency_ms": 0.0,
            "error": None,
        }

    output = tmp_path / "run"
    summary = run_experiment(
        source_document=source,
        gold_document=gold,
        distractor_document=distractors,
        oracle_representation_document=representations,
        oracle_query_plan_document=query_plans,
        output_dir=output,
        encoder=FakeEncoder(),
        config=ExperimentRunConfig(
            run_id="run-20260725T120015Z",
            workers=1,
            arms=("B0",),
            tracks=("oracle",),
            scales=(50,),
        ),
        execute=execute,
    )
    assert summary.error_count == 0
    row = json.loads((output / "results.jsonl").read_text(encoding="utf-8"))
    assert row["error"] is None
    assert verify_run(output)["status"] == "valid"


def test_verify_run_rejects_duplicate_or_missing_grid_cells(tmp_path: Path) -> None:
    source, gold, distractors, representations, query_plans = _single_scenario_documents()

    def execute(**kwargs):
        return {
            "selected_evidence_turn_ids": [],
            "ranked_evidence": [],
            "predicted_answer": None,
            "abstained": True,
            "constraint_checks": {},
            "symbolic_trace": [],
            "fallback": {"triggered": False, "reason": None, "rejected_candidates": []},
            "latency_ms": 0.0,
            "error": None,
        }

    output = tmp_path / "run"
    run_experiment(
        source_document=source,
        gold_document=gold,
        distractor_document=distractors,
        oracle_representation_document=representations,
        oracle_query_plan_document=query_plans,
        output_dir=output,
        encoder=FakeEncoder(),
        config=ExperimentRunConfig(
            run_id="run-20260725T120009Z",
            workers=1,
            arms=("B0", "B1"),
            tracks=("oracle",),
            scales=(0,),
        ),
        execute=execute,
    )
    result_path = output / "results.jsonl"
    rows = [json.loads(line) for line in result_path.read_text(encoding="utf-8").splitlines()]
    rows[-1] = copy.deepcopy(rows[-2])
    result_bytes = b"".join((json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n").encode() for row in rows)
    result_path.write_bytes(result_bytes)
    manifest_path = output / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["results_sha256"] = hashlib.sha256(result_bytes).hexdigest()
    manifest_path.write_text(json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate|missing"):
        verify_run(output)


def test_verify_run_rejects_wrong_run_id_invalid_evidence_and_error_count(tmp_path: Path) -> None:
    source, gold, distractors, representations, query_plans = _single_scenario_documents()

    def execute(**kwargs):
        return {
            "selected_evidence_turn_ids": [],
            "ranked_evidence": [],
            "predicted_answer": None,
            "abstained": True,
            "constraint_checks": {},
            "symbolic_trace": [],
            "fallback": {"triggered": False, "reason": None, "rejected_candidates": []},
            "latency_ms": 0.0,
            "error": None,
        }

    output = tmp_path / "run"
    run_experiment(
        source_document=source,
        gold_document=gold,
        distractor_document=distractors,
        oracle_representation_document=representations,
        oracle_query_plan_document=query_plans,
        output_dir=output,
        encoder=FakeEncoder(),
        config=ExperimentRunConfig(run_id="run-20260725T120010Z", workers=1, arms=("B0",), tracks=("oracle",), scales=(0,)),
        execute=execute,
    )

    result_path = output / "results.jsonl"
    rows = [json.loads(line) for line in result_path.read_text(encoding="utf-8").splitlines()]
    rows[0]["run_id"] = "run-other"
    rows[0]["selected_evidence_turn_ids"] = ["OME-S001-T99"]
    rows[0]["status"] = "error"
    rows[0]["error"] = "fixture error"
    result_bytes = b"".join((json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n").encode() for row in rows)
    result_path.write_bytes(result_bytes)
    manifest_path = output / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["results_sha256"] = hashlib.sha256(result_bytes).hexdigest()
    manifest_path.write_text(json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="run_id|evidence|error_count"):
        verify_run(output)
