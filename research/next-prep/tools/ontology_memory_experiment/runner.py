"""Deterministic, bounded-concurrency orchestration for the controlled experiment."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from itertools import product
from dataclasses import dataclass
import hashlib
import inspect
import json
from pathlib import Path
from time import perf_counter
from typing import Any, Callable, Mapping, Sequence

from tools.ontology_memory_experiment.query import compile_query
from tools.ontology_memory_experiment.representations import (
    build_distractor_representations,
    build_representations,
)


ARMS = ("B0", "B1", "B2", "O-", "O+", "O+E")
TRACKS = ("oracle", "automatic")
SCALES = (0, 50, 500)


@dataclass(frozen=True, slots=True)
class ExperimentRunConfig:
    run_id: str
    workers: int = 4
    arms: tuple[str, ...] = ARMS
    tracks: tuple[str, ...] = TRACKS
    scales: tuple[int, ...] = SCALES

    def __post_init__(self) -> None:
        if not self.run_id.startswith("run-"):
            raise ValueError("run_id must start with run-")
        if self.workers < 1:
            raise ValueError("workers must be positive")
        if not self.arms or any(arm not in ARMS for arm in self.arms):
            raise ValueError("config contains an unknown arm")
        if not self.tracks or any(track not in TRACKS for track in self.tracks):
            raise ValueError("config contains an unknown track")
        if not self.scales or any(scale not in SCALES for scale in self.scales):
            raise ValueError("config contains an unknown distractor scale")


@dataclass(frozen=True, slots=True)
class RunSummary:
    run_id: str
    result_count: int
    error_count: int
    output_dir: Path


ExecuteFunction = Callable[..., Mapping[str, Any]]


def _plain(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    return value


def _canonical_bytes(value: Any) -> bytes:
    return (json.dumps(_plain(value), ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode(
        "utf-8"
    )


def _sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _write_new(path: Path, content: bytes) -> None:
    if path.exists():
        raise ValueError(f"refusing to overwrite existing run artifact: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def _model_metadata(encoder: Any) -> dict[str, Any]:
    metadata = getattr(encoder, "model_metadata", None)
    if isinstance(metadata, Mapping):
        result = dict(metadata)
    else:
        result = {
            "model_id": str(getattr(encoder, "model_id", "unknown")),
            "revision": str(getattr(encoder, "revision", "unknown")),
            "dimensions": int(getattr(encoder, "dimensions", 0)),
        }
    for field in ("cache_hits", "cache_misses", "encoded_text_count"):
        value = getattr(encoder, field, None)
        if value is not None:
            result[field] = int(value)
    return result


def _contains_forbidden_fixture_field(value: Any) -> str | None:
    forbidden = {
        "answer",
        "required_evidence_turn_ids",
        "hard_negative_turn_ids",
        "family",
        "split",
        "primary_system",
        "architecture_claim_ids",
    }
    if isinstance(value, Mapping):
        for key, child in value.items():
            if key in forbidden:
                return str(key)
            found = _contains_forbidden_fixture_field(child)
            if found:
                return found
    elif isinstance(value, list):
        for child in value:
            found = _contains_forbidden_fixture_field(child)
            if found:
                return found
    return None


def _index_oracle_representations(document: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    forbidden = _contains_forbidden_fixture_field(document)
    if forbidden:
        raise ValueError(f"oracle fixture contains forbidden gold field: {forbidden}")
    scenarios = document.get("scenarios")
    if not isinstance(scenarios, list):
        raise ValueError("oracle representation document must contain scenarios")
    result: dict[str, Mapping[str, Any]] = {}
    for fixture in scenarios:
        if not isinstance(fixture, Mapping) or not isinstance(fixture.get("scenario_id"), str):
            raise ValueError("oracle representation scenario is invalid")
        scenario_id = str(fixture["scenario_id"])
        if scenario_id in result:
            raise ValueError(f"duplicate oracle representation: {scenario_id}")
        if not isinstance(fixture.get("records"), list):
            raise ValueError(f"oracle representation {scenario_id} requires records")
        if not isinstance(fixture.get("ablated_records"), list):
            raise ValueError(f"oracle representation {scenario_id} requires ablated_records")
        result[scenario_id] = fixture
    return result


def _index_oracle_query_plans(document: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    forbidden = _contains_forbidden_fixture_field(document)
    if forbidden:
        raise ValueError(f"oracle query plan contains forbidden gold field: {forbidden}")
    scenarios = document.get("scenarios")
    if not isinstance(scenarios, list):
        raise ValueError("oracle query-plan document must contain scenarios")
    result: dict[str, Mapping[str, Any]] = {}
    for fixture in scenarios:
        if not isinstance(fixture, Mapping) or not isinstance(fixture.get("scenario_id"), str):
            raise ValueError("oracle query-plan scenario is invalid")
        scenario_id = str(fixture["scenario_id"])
        if scenario_id in result:
            raise ValueError(f"duplicate oracle query plan: {scenario_id}")
        if not isinstance(fixture.get("query_plan"), Mapping):
            raise ValueError(f"oracle query-plan {scenario_id} requires query_plan")
        result[scenario_id] = fixture
    return result


def _infer_ablation_field(representation: Mapping[str, Any]) -> str:
    records = representation.get("records")
    ablated = representation.get("ablated_records")
    if not isinstance(records, list) or not isinstance(ablated, list) or len(records) != len(ablated):
        raise ValueError("oracle ablation requires aligned records")
    ignored = {"record_id", "source_turn_ids", "surface_text"}
    changed = {
        key
        for full, reduced in zip(records, ablated, strict=True)
        if isinstance(full, Mapping) and isinstance(reduced, Mapping)
        for key in set(full) | set(reduced)
        if key not in ignored and full.get(key) != reduced.get(key)
    }
    if len(changed) != 1:
        raise ValueError(f"oracle ablation must change exactly one representation field, got {sorted(changed)}")
    return next(iter(changed))


def _raw_records(scenario: Mapping[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "record_id": str(turn["turn_id"]),
            "source_turn_ids": [str(turn["turn_id"])],
            "surface_text": str(turn["text"]),
            "entities": [],
            "predicate": None,
            "roles": {},
            "polarity": None,
            "modality": None,
            "quantity": None,
            "valid_time": None,
            "transaction_time": None,
            "provenance_status": None,
            "conflict_group": None,
            "supersedes": [],
            "relations": [],
        }
        for turn in scenario.get("turns", [])
    ]


def _distractor_records(records: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "record_id": str(record["record_id"]),
            "source_turn_ids": [str(record["record_id"])],
            "surface_text": str(record.get("text", "")),
            "entities": [],
            "predicate": None,
            "roles": {},
            "polarity": None,
            "modality": None,
            "quantity": None,
            "valid_time": None,
            "transaction_time": None,
            "provenance_status": None,
            "conflict_group": None,
            "supersedes": [],
            "relations": [],
        }
        for record in records
    ]


_TYPED_RECORD_FIELDS = {
    "entities",
    "predicate",
    "roles",
    "polarity",
    "modality",
    "quantity",
    "valid_time",
    "transaction_time",
    "provenance_status",
    "lifecycle_status",
    "conflict_group",
    "supersedes",
    "derived_from",
    "absent_slots",
    "relations",
}


def _distractor_fixture_index(
    fixture: Mapping[str, Any],
    track: str,
    scale: int | None = None,
) -> dict[str, Mapping[str, Any]]:
    """Return optional typed distractor records keyed by distractor ID.

    The frozen distractor document intentionally contains only source text. A
    representation fixture may provide semantic records under either the
    track-specific key or the shared ``distractor_records`` key. The runner
    keeps this hook generic so a future fixture can add typed distractors
    without changing the source document schema.
    """
    value = fixture.get(f"{track}_distractor_records")
    if value is None:
        value = fixture.get("distractor_records", [])
    if value is None:
        return {}
    if isinstance(value, Mapping):
        # v2 fixtures are nested as {"50": [...], "500": [...]}. Keep
        # support for a flat {record_id: record} extension as well.
        scale_key = str(scale) if scale is not None else None
        if not value:
            value = []
        elif scale_key is not None and (scale_key in value or scale in value):
            value = value[scale_key] if scale_key in value else value[scale]
        elif value and all(isinstance(item, Mapping) for item in value.values()):
            value = list(value.values())
        else:
            nested: list[Any] = []
            for child in value.values():
                if isinstance(child, list):
                    nested.extend(child)
                elif isinstance(child, Mapping):
                    nested.extend(child.values())
                else:
                    raise ValueError("typed distractor scale mapping values must be lists or mappings")
            value = nested
        if isinstance(value, Mapping):
            value = list(value.values())
        values = value
    elif isinstance(value, list):
        values = value
    else:
        raise ValueError("typed distractor fixture must be a list or mapping")
    result: dict[str, Mapping[str, Any]] = {}
    for item in values:
        if not isinstance(item, Mapping) or not isinstance(item.get("record_id"), str):
            raise ValueError("typed distractor fixture records require record_id")
        record_id = str(item["record_id"])
        if record_id in result:
            raise ValueError(f"duplicate typed distractor record: {record_id}")
        if not _TYPED_RECORD_FIELDS.intersection(item):
            raise ValueError(f"typed distractor {record_id} has no semantic fields")
        result[record_id] = item
    return result


def _typed_distractor_records(
    records: Sequence[Mapping[str, Any]],
    fixture_records: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for record in records:
        record_id = str(record["record_id"])
        typed = fixture_records.get(record_id)
        if typed is None:
            if not _TYPED_RECORD_FIELDS.intersection(record):
                raise ValueError(
                    f"typed distractor fixture required for symbolic arm: {record_id}"
                )
            typed = record
        item = dict(typed)
        item.setdefault("record_id", record_id)
        item.setdefault("source_turn_ids", [record_id])
        item.setdefault("surface_text", str(record.get("text", record.get("surface_text", ""))))
        result.append(item)
    return result


def _token_count(text: Any) -> int:
    return len(str(text).split())


def _source_turn_texts(scenario: Mapping[str, Any]) -> dict[str, str]:
    turns = scenario.get("turns")
    if not isinstance(turns, list):
        raise ValueError(f"scenario {scenario.get('scenario_id')} requires turns")
    result: dict[str, str] = {}
    for turn in turns:
        if not isinstance(turn, Mapping) or not isinstance(turn.get("turn_id"), str):
            raise ValueError("source turn is invalid")
        turn_id = str(turn["turn_id"])
        if turn_id in result:
            raise ValueError(f"duplicate source turn: {turn_id}")
        result[turn_id] = str(turn.get("text", ""))
    return result


def _validate_source_budgets(
    scenarios: Sequence[Mapping[str, Any]],
    gold_by_id: Mapping[str, Mapping[str, Any]],
) -> None:
    for scenario in scenarios:
        scenario_id = str(scenario["scenario_id"])
        budget = scenario.get("candidate_answer_budget")
        if not isinstance(budget, int) or budget < 1:
            raise ValueError(f"scenario {scenario_id} has invalid candidate_answer_budget")
        turn_texts = _source_turn_texts(scenario)
        required = gold_by_id[scenario_id].get("required_evidence_turn_ids", [])
        unknown = [str(turn_id) for turn_id in required if str(turn_id) not in turn_texts]
        if unknown:
            raise ValueError(f"scenario {scenario_id} has unknown required evidence: {unknown}")
        required_tokens = sum(_token_count(turn_texts[str(turn_id)]) for turn_id in required)
        if required_tokens > budget:
            raise ValueError(
                f"scenario {scenario_id} candidate budget {budget} is below required evidence tokens {required_tokens}"
            )


def _selected_evidence_tokens(
    selected_ids: Sequence[Any],
    turn_texts: Mapping[str, str],
) -> int:
    ids = [str(value) for value in selected_ids]
    if len(set(ids)) != len(ids):
        raise ValueError("selected evidence IDs must be unique")
    unknown = [value for value in ids if value not in turn_texts]
    if unknown:
        raise ValueError(f"selected evidence contains unknown turn IDs: {unknown}")
    return sum(_token_count(turn_texts[value]) for value in ids)


def _normalize_executor_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Keep the scoring-facing legacy fields while filling the result contract.

    ``execute_arm`` predates the strict result model and intentionally returns
    a few convenience fields (``abstained`` and the fallback object). This
    boundary normalizes malformed optional values without granting an
    executor access to gold annotations.
    """
    result = dict(payload)
    selected = result.get("selected_evidence_turn_ids", [])
    if not isinstance(selected, list):
        raise ValueError("selected_evidence_turn_ids must be a list")
    result.setdefault("ranked_evidence", [])
    result.setdefault("predicted_answer", None)
    result.setdefault("abstained", result.get("predicted_answer") is None)
    if not isinstance(result.get("ranked_evidence"), list):
        raise ValueError("ranked_evidence must be a list")
    if not isinstance(result.get("constraint_checks"), Mapping):
        result["constraint_checks"] = {}
    if not isinstance(result.get("symbolic_trace"), list):
        result["symbolic_trace"] = []
    fallback = result.get("fallback")
    if not isinstance(fallback, Mapping):
        fallback = {"triggered": bool(result.get("fallback_trigger")), "reason": result.get("fallback_reason"), "rejected_candidates": []}
    result["fallback"] = dict(fallback)
    result.setdefault("rejected_fallback_candidates", list(result["fallback"].get("rejected_candidates", [])))
    result.setdefault("latency_ms", None)
    result.setdefault("error", None)
    return result


def _index_gold(gold_document: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    scenarios = gold_document.get("scenarios")
    if not isinstance(scenarios, list):
        raise ValueError("gold document must contain scenarios")
    result: dict[str, Mapping[str, Any]] = {}
    for item in scenarios:
        if not isinstance(item, Mapping) or not isinstance(item.get("scenario_id"), str):
            raise ValueError("gold scenario is invalid")
        scenario_id = item["scenario_id"]
        if scenario_id in result:
            raise ValueError(f"duplicate gold scenario: {scenario_id}")
        result[scenario_id] = item
    return result


def _index_distractors(document: Mapping[str, Any]) -> dict[tuple[str, int], list[Mapping[str, Any]]]:
    records = document.get("records")
    if not isinstance(records, list):
        raise ValueError("distractor document must contain records")
    result: dict[tuple[str, int], list[Mapping[str, Any]]] = {}
    for record in records:
        if not isinstance(record, Mapping):
            raise ValueError("distractor record is invalid")
        scenario_id = record.get("scenario_id")
        scale = record.get("distractor_scale", record.get("scale"))
        if not isinstance(scenario_id, str) or not isinstance(scale, int):
            raise ValueError("distractor record requires scenario_id and scale")
        result.setdefault((scenario_id, scale), []).append(record)
    for values in result.values():
        values.sort(key=lambda item: str(item.get("record_id")))
    return result


def run_experiment(
    *,
    source_document: Any,
    gold_document: Any,
    distractor_document: Any,
    oracle_representation_document: Any,
    oracle_query_plan_document: Any,
    output_dir: str | Path,
    encoder: Any,
    config: ExperimentRunConfig,
    execute: ExecuteFunction,
    clock: Callable[[], float] = perf_counter,
) -> RunSummary:
    source = _plain(source_document)
    gold = _plain(gold_document)
    distractors = _plain(distractor_document)
    oracle_representations = _plain(oracle_representation_document)
    oracle_query_plans = _plain(oracle_query_plan_document)
    documents = (source, gold, distractors, oracle_representations, oracle_query_plans)
    if not all(isinstance(value, Mapping) for value in documents):
        raise ValueError("source, gold, distractors, and oracle documents must be mappings")
    output = Path(output_dir)
    if output.exists() and any(output.iterdir()):
        raise ValueError(f"refusing to overwrite existing run directory: {output}")
    scenarios = source.get("scenarios")
    if not isinstance(scenarios, list):
        raise ValueError("source document must contain scenarios")
    gold_by_id = _index_gold(gold)
    distractors_by_key = _index_distractors(distractors)
    representations_by_id = _index_oracle_representations(oracle_representations)
    query_plans_by_id = _index_oracle_query_plans(oracle_query_plans)
    source_ids = {scenario.get("scenario_id") for scenario in scenarios if isinstance(scenario, Mapping)}
    if source_ids != set(gold_by_id):
        raise ValueError("source and gold scenarios must exactly match")
    if source_ids != set(representations_by_id) or source_ids != set(query_plans_by_id):
        raise ValueError("source and oracle scenarios must exactly match")
    _validate_source_budgets(scenarios, gold_by_id)

    tasks: list[tuple[Mapping[str, Any], Mapping[str, Any], str, str, int, list[Mapping[str, Any]]]] = []
    for scenario in scenarios:
        if not isinstance(scenario, Mapping):
            raise ValueError("source scenario is invalid")
        scenario_id = scenario.get("scenario_id")
        question = scenario.get("question")
        if not isinstance(scenario_id, str) or not isinstance(question, str):
            raise ValueError("source scenario requires scenario_id and question")
        fixture = {
            **representations_by_id[scenario_id],
            "query_plan": query_plans_by_id[scenario_id]["query_plan"],
        }
        for track in config.tracks:
            for arm in config.arms:
                for scale in config.scales:
                    selected = [] if scale == 0 else distractors_by_key.get((scenario_id, scale), [])
                    if len(selected) != scale:
                        raise ValueError(
                            f"scenario {scenario_id} scale {scale} has {len(selected)} distractors"
                        )
                    tasks.append((scenario, fixture, track, arm, scale, selected))

    def invoke(task: tuple[Mapping[str, Any], Mapping[str, Any], str, str, int, list[Mapping[str, Any]]]):
        scenario, fixture, track, arm, scale, selected = task
        scenario_id = str(scenario["scenario_id"])
        elapsed_ms: float | None = None
        representation_latency_ms: float | None = None
        query_compile_latency_ms: float | None = None
        turn_texts = _source_turn_texts(scenario)
        evidence_texts = dict(turn_texts)
        for distractor in selected:
            if isinstance(distractor, Mapping) and isinstance(distractor.get("record_id"), str):
                evidence_texts[str(distractor["record_id"])] = str(distractor.get("text", ""))
        try:
            if track == "oracle":
                if arm == "B0":
                    records = _raw_records(scenario)
                elif arm == "O-":
                    records = list(fixture["ablated_records"])
                else:
                    records = list(fixture["records"])
                query_plan = dict(fixture["query_plan"])
                distractor_records: list[dict[str, Any]] | None = None
            else:
                ablation = _infer_ablation_field(fixture) if arm == "O-" else None
                representation_started_at = clock()
                if arm == "B0":
                    records = _raw_records(scenario)
                else:
                    records = build_representations(scenario, "automatic", ablate_primitive=ablation)
                if scale and arm in {"O-", "O+", "O+E"}:
                    distractor_records = build_distractor_representations(selected)
                else:
                    distractor_records = None
                representation_finished_at = clock()
                representation_latency_ms = max(0.0, (representation_finished_at - representation_started_at) * 1000.0)
                query_started_at = representation_finished_at
                query_plan = compile_query(str(scenario["question"]), "automatic")
                query_compile_latency_ms = max(0.0, (clock() - query_started_at) * 1000.0)
            if distractor_records is None:
                typed_distractor_index = _distractor_fixture_index(fixture, track, scale)
                if scale and arm in {"O-", "O+", "O+E"}:
                    distractor_records = _typed_distractor_records(selected, typed_distractor_index)
                else:
                    distractor_records = _distractor_records(selected)
            started_at = clock()
            try:
                execute_kwargs = {
                    "arm": arm,
                    "scenario": scenario,
                    "records": records,
                    "query_plan": query_plan,
                    "distractors": tuple(distractor_records),
                    "encoder": encoder,
                }
                signature = inspect.signature(execute)
                if "track" in signature.parameters or any(
                    parameter.kind is inspect.Parameter.VAR_KEYWORD
                    for parameter in signature.parameters.values()
                ):
                    execute_kwargs["track"] = track
                if "evidence_token_budget" in signature.parameters or any(
                    parameter.kind is inspect.Parameter.VAR_KEYWORD
                    for parameter in signature.parameters.values()
                ):
                    execute_kwargs["evidence_token_budget"] = int(scenario["candidate_answer_budget"])
                payload = _normalize_executor_payload(execute(**execute_kwargs))
            finally:
                elapsed_ms = max(0.0, (clock() - started_at) * 1000.0)
            selected_ids = payload.get("selected_evidence_turn_ids", [])
            if not isinstance(selected_ids, list):
                raise ValueError("selected_evidence_turn_ids must be a list")
            evidence_tokens = _selected_evidence_tokens(selected_ids, evidence_texts)
            budget = int(scenario["candidate_answer_budget"])
            if evidence_tokens > budget:
                raise ValueError(
                    f"selected evidence uses {evidence_tokens} tokens, above candidate budget {budget}"
                )
        except Exception as error:  # The immutable ledger keeps one row per attempted arm.
            payload = {
                "selected_evidence_turn_ids": [],
                "ranked_evidence": [],
                "predicted_answer": None,
                "abstained": True,
                "constraint_checks": [],
                "symbolic_trace": [],
                "fallback": {"triggered": False, "reason": None, "rejected_candidates": []},
                "latency_ms": None,
                "error": f"{type(error).__name__}: {error}",
            }
        payload["executor_latency_ms"] = payload.get("latency_ms")
        payload["latency_ms"] = elapsed_ms
        payload["representation_latency_ms"] = representation_latency_ms
        payload["query_compile_latency_ms"] = query_compile_latency_ms
        payload["status"] = "error" if payload.get("error") else ("abstained" if payload.get("abstained") else "ok")
        return {
            "schema_version": "ontology-memory-result-v1",
            "run_id": config.run_id,
            "scenario_id": scenario_id,
            "track": track,
            "arm": arm,
            "distractor_scale": scale,
            **payload,
        }

    with ThreadPoolExecutor(max_workers=config.workers, thread_name_prefix="ome") as pool:
        rows = list(pool.map(invoke, tasks))
    rows.sort(key=lambda row: (row["scenario_id"], row["track"], row["arm"], row["distractor_scale"]))
    final_model_metadata = _model_metadata(encoder)

    input_documents = {
        "source": source,
        "gold": gold,
        "distractors": distractors,
        "oracle-representations": oracle_representations,
        "oracle-query-plans": oracle_query_plans,
    }
    for name, document in input_documents.items():
        _write_new(output / "inputs" / f"{name}.json", _canonical_bytes(document))
    results_content = b"".join(_canonical_bytes(row) for row in rows)
    results_path = output / "results.jsonl"
    _write_new(results_path, results_content)
    errors = [row for row in rows if row.get("error")]
    errors_content = b"".join(_canonical_bytes(row) for row in errors)
    _write_new(output / "errors.jsonl", errors_content)
    manifest = {
        "schema_version": "ontology-memory-run-manifest-v1",
        "run_id": config.run_id,
        "source_sha256": _sha256(source),
        "gold_sha256": _sha256(gold),
        "distractors_sha256": _sha256(distractors),
        "oracle_representations_sha256": _sha256(oracle_representations),
        "oracle_query_plans_sha256": _sha256(oracle_query_plans),
        "results_sha256": hashlib.sha256(results_content).hexdigest(),
        "errors_sha256": hashlib.sha256(errors_content).hexdigest(),
        "result_count": len(rows),
        "error_count": len(errors),
        "arms": list(config.arms),
        "tracks": list(config.tracks),
        "scales": list(config.scales),
        "workers": config.workers,
        "model": final_model_metadata,
    }
    _write_new(output / "manifest.json", _canonical_bytes(manifest))
    return RunSummary(config.run_id, len(rows), len(errors), output)


def verify_run(run_dir: str | Path) -> dict[str, Any]:
    directory = Path(run_dir)
    manifest_path = directory / "manifest.json"
    results_path = directory / "results.jsonl"
    errors_path = directory / "errors.jsonl"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"could not read run manifest: {error}") from error
    for path, field in ((results_path, "results_sha256"), (errors_path, "errors_sha256")):
        try:
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
        except OSError as error:
            raise ValueError(f"could not read {path}: {error}") from error
        if digest != manifest.get(field):
            raise ValueError(f"{field} does not match artifact sha256")
    if not isinstance(manifest.get("run_id"), str) or not manifest["run_id"].startswith("run-"):
        raise ValueError("manifest run_id is invalid")
    for field in ("arms", "tracks", "scales"):
        values = manifest.get(field)
        if not isinstance(values, list) or not values or len(set(values)) != len(values):
            raise ValueError(f"manifest {field} coverage is invalid")
    if any(arm not in ARMS for arm in manifest["arms"]):
        raise ValueError("manifest arm coverage contains an unknown arm")
    if any(track not in TRACKS for track in manifest["tracks"]):
        raise ValueError("manifest track coverage contains an unknown track")
    if any(scale not in SCALES for scale in manifest["scales"]):
        raise ValueError("manifest scale coverage contains an unknown scale")
    for name, field in (
        ("source", "source_sha256"),
        ("gold", "gold_sha256"),
        ("distractors", "distractors_sha256"),
        ("oracle-representations", "oracle_representations_sha256"),
        ("oracle-query-plans", "oracle_query_plans_sha256"),
    ):
        path = directory / "inputs" / f"{name}.json"
        try:
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
        except OSError as error:
            raise ValueError(f"could not read input {path}: {error}") from error
        if digest != manifest.get(field):
            raise ValueError(f"{field} does not match input sha256")
    try:
        source_input = json.loads((directory / "inputs" / "source.json").read_text(encoding="utf-8"))
        gold_input = json.loads((directory / "inputs" / "gold.json").read_text(encoding="utf-8"))
        distractor_input = json.loads((directory / "inputs" / "distractors.json").read_text(encoding="utf-8"))
        rows = [json.loads(line) for line in results_path.read_text(encoding="utf-8").splitlines() if line]
        error_rows = [json.loads(line) for line in errors_path.read_text(encoding="utf-8").splitlines() if line]
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"run result artifacts are not valid JSON: {error}") from error
    if len(rows) != manifest.get("result_count"):
        raise ValueError("result_count does not match results artifact")
    if not isinstance(source_input, Mapping) or not isinstance(gold_input, Mapping):
        raise ValueError("source and gold input snapshots are invalid")
    source_scenarios = source_input.get("scenarios")
    gold_scenarios = gold_input.get("scenarios")
    if not isinstance(source_scenarios, list) or not isinstance(gold_scenarios, list):
        raise ValueError("source and gold snapshots require scenarios")
    scenario_ids = {
        str(item.get("scenario_id"))
        for item in source_scenarios
        if isinstance(item, Mapping) and isinstance(item.get("scenario_id"), str)
    }
    gold_by_id = {
        str(item.get("scenario_id")): item
        for item in gold_scenarios
        if isinstance(item, Mapping) and isinstance(item.get("scenario_id"), str)
    }
    if scenario_ids != set(gold_by_id):
        raise ValueError("source and gold scenario coverage does not match")
    distractor_ids_by_key: dict[tuple[str, int], set[str]] = {}
    distractor_records = distractor_input.get("records") if isinstance(distractor_input, Mapping) else None
    if not isinstance(distractor_records, list):
        raise ValueError("distractor snapshot requires records")
    for distractor in distractor_records:
        if not isinstance(distractor, Mapping):
            raise ValueError("distractor snapshot record is invalid")
        scenario_id = distractor.get("scenario_id")
        scale = distractor.get("distractor_scale", distractor.get("scale"))
        record_id = distractor.get("record_id")
        if not isinstance(scenario_id, str) or not isinstance(scale, int) or not isinstance(record_id, str):
            raise ValueError("distractor snapshot record requires scenario_id, scale, and record_id")
        distractor_ids_by_key.setdefault((scenario_id, scale), set()).add(record_id)
    turn_ids_by_scenario: dict[str, set[str]] = {}
    for scenario in source_scenarios:
        if not isinstance(scenario, Mapping):
            raise ValueError("source scenario snapshot is invalid")
        scenario_id = str(scenario["scenario_id"])
        turn_ids_by_scenario[scenario_id] = {
            str(turn["turn_id"])
            for turn in scenario.get("turns", [])
            if isinstance(turn, Mapping) and isinstance(turn.get("turn_id"), str)
        }
    expected_cells = {
        (scenario_id, track, arm, scale)
        for scenario_id, track, arm, scale in product(
            sorted(scenario_ids), manifest["tracks"], manifest["arms"], manifest["scales"]
        )
    }
    actual_cells: list[tuple[str, str, str, int]] = []
    for row in rows:
        if not isinstance(row, Mapping):
            raise ValueError("result row is not an object")
        required = {
            "schema_version",
            "run_id",
            "scenario_id",
            "track",
            "arm",
            "distractor_scale",
            "ranked_evidence",
            "selected_evidence_turn_ids",
            "predicted_answer",
            "abstained",
            "constraint_checks",
            "symbolic_trace",
            "fallback",
            "latency_ms",
            "executor_latency_ms",
            "representation_latency_ms",
            "query_compile_latency_ms",
            "status",
            "error",
        }
        missing = sorted(required.difference(row))
        if missing:
            raise ValueError(f"result row is missing fields: {missing}")
        if row["schema_version"] != "ontology-memory-result-v1":
            raise ValueError("result row schema_version is invalid")
        if row["run_id"] != manifest["run_id"]:
            raise ValueError("result row run_id does not match manifest")
        key = (str(row["scenario_id"]), str(row["track"]), str(row["arm"]), row["distractor_scale"])
        actual_cells.append(key)
        if key[0] not in turn_ids_by_scenario:
            raise ValueError(f"result row references unknown scenario: {key[0]}")
        if key[1] not in manifest["tracks"] or key[2] not in manifest["arms"] or key[3] not in manifest["scales"]:
            raise ValueError(f"result row is outside manifest grid: {key}")
        if row["status"] not in {"ok", "abstained", "error"}:
            raise ValueError(f"result row status is invalid: {row['status']}")
        if bool(row.get("error")) != (row["status"] == "error"):
            raise ValueError("result error/status mismatch")
        selected = row["selected_evidence_turn_ids"]
        if not isinstance(selected, list):
            raise ValueError("selected evidence IDs must be a list")
        if not isinstance(row["ranked_evidence"], list):
            raise ValueError("ranked_evidence must be a list")
        if not isinstance(row["constraint_checks"], Mapping):
            raise ValueError("constraint_checks must be an object")
        if not isinstance(row["symbolic_trace"], list):
            raise ValueError("symbolic_trace must be a list")
        if not isinstance(row["fallback"], Mapping):
            raise ValueError("fallback must be an object")
        allowed_evidence = set(turn_ids_by_scenario[key[0]])
        allowed_evidence.update(distractor_ids_by_key.get((key[0], int(key[3])), set()))
        unknown_evidence = sorted(set(str(value) for value in selected) - allowed_evidence)
        if unknown_evidence:
            raise ValueError(f"result row contains invalid evidence IDs: {unknown_evidence}")
    if len(actual_cells) != len(set(actual_cells)):
        raise ValueError("result grid contains duplicate cells")
    if set(actual_cells) != expected_cells:
        missing = sorted(expected_cells - set(actual_cells))
        extra = sorted(set(actual_cells) - expected_cells)
        raise ValueError(f"result grid coverage is incomplete; missing={missing}, extra={extra}")
    expected_error_keys = {
        (str(row["scenario_id"]), str(row["track"]), str(row["arm"]), row["distractor_scale"])
        for row in rows
        if bool(row.get("error"))
    }
    actual_error_keys = {
        (str(row.get("scenario_id")), str(row.get("track")), str(row.get("arm")), row.get("distractor_scale"))
        for row in error_rows
    }
    if len(error_rows) != manifest.get("error_count"):
        raise ValueError("error_count does not match errors artifact")
    if actual_error_keys != expected_error_keys or len(actual_error_keys) != len(error_rows):
        raise ValueError("errors artifact does not match result error rows")
    return {
        "status": "valid",
        "run_id": manifest.get("run_id"),
        "result_count": len(rows),
        "error_count": len(error_rows),
        "gold_sha256": manifest.get("gold_sha256"),
    }
