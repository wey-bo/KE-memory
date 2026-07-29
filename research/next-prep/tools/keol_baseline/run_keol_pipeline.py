from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from .keol_ke_test_adapter import (
    KEOL_COMMIT,
    build_turn_units,
    materialize_keol_dataset,
    merge_model_graph_batches,
    validate_model_graphs,
)


SOURCE_PATH = Path("data/gold-candidates/KE-test.json")
BASELINE_ROOT = Path("artifacts/keol-baseline")


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_normalization_payloads(
    result: Any,
    keol_root: Path,
    output_dir: Path,
    *,
    batch_size: int = 40,
) -> list[Path]:
    if batch_size < 1:
        raise ValueError("batch_size must be positive")
    keol_src = keol_root / "src"
    sys.path.insert(0, str(keol_src))
    try:
        from onto.normalizer import build_normalization_payload

        batch_count = max(
            (len(result.concepts) + batch_size - 1) // batch_size,
            (len(result.operators) + batch_size - 1) // batch_size,
        )
        paths: list[Path] = []
        for batch_index in range(batch_count):
            offset = batch_index * batch_size
            payload = build_normalization_payload(
                result,
                concept_limit=batch_size,
                operator_limit=batch_size,
                concept_offset=offset,
                operator_offset=offset,
            )
            payload["keol_commit"] = KEOL_COMMIT
            payload["batch_index"] = batch_index
            path = output_dir / f"payload-{batch_index:03d}.json"
            _write_json(path, payload)
            paths.append(path)
        return paths
    finally:
        sys.path.remove(str(keol_src))


def apply_normalization_plan_files(
    result: Any,
    keol_root: Path,
    payload_paths: list[Path],
    plan_paths: list[Path],
) -> list[dict[str, Any]]:
    if len(payload_paths) != len(plan_paths):
        raise ValueError("normalization payload/plan counts differ")
    seeded_concept_ids = {item.id for item in result.concepts if item.source_kind == "seeded"}
    seeded_operator_ids = {item.id for item in result.operators if item.source_kind == "seeded"}
    keol_src = keol_root / "src"
    sys.path.insert(0, str(keol_src))
    try:
        from onto.normalizer import NormalizationPlan, apply_normalization_plan

        batch_stats: list[dict[str, Any]] = []
        for payload_path, plan_path in zip(payload_paths, plan_paths):
            payload = _read_json(payload_path)
            plan_data = _read_json(plan_path)
            allowed_concepts = {item["id"] for item in payload.get("concepts", [])}
            allowed_operators = {item["id"] for item in payload.get("operators", [])}
            concept_ids = [item.get("id") for item in plan_data.get("concept_updates", [])]
            operator_ids = [item.get("id") for item in plan_data.get("operator_updates", [])]
            if len(concept_ids) != len(set(concept_ids)) or set(concept_ids) != allowed_concepts:
                raise ValueError(
                    f"normalization concept ID coverage mismatch in {plan_path.name}"
                )
            if len(operator_ids) != len(set(operator_ids)) or set(operator_ids) != allowed_operators:
                raise ValueError(
                    f"normalization operator ID coverage mismatch in {plan_path.name}"
                )
            plan = NormalizationPlan.model_validate(plan_data)
            apply_normalization_plan(result, plan)
            stats = dict(
                result.workflow_runs[0].metadata.get("llm_normalization", {})
                if result.workflow_runs
                else {}
            )
            stats.update(
                {
                    "model": "codex_subagent",
                    "batch_index": payload.get("batch_index"),
                    "payload": payload_path.name,
                    "plan": plan_path.name,
                }
            )
            batch_stats.append(stats)
        for concept in result.concepts:
            if concept.id in seeded_concept_ids:
                concept.source_kind = "seeded"
        for operator in result.operators:
            if operator.id in seeded_operator_ids:
                operator.source_kind = "seeded"
        if result.workflow_runs:
            result.workflow_runs[0].metadata["llm_normalization"] = {
                "model": "codex_subagent",
                "status": "succeeded",
                "batch_count": len(batch_stats),
                "batches": batch_stats,
            }
        return batch_stats
    finally:
        sys.path.remove(str(keol_src))


def run_pipeline(
    workspace: Path,
    keol_root: Path,
    *,
    dataset_name: str = "KE-test",
) -> dict[str, Any]:
    baseline_root = workspace / BASELINE_ROOT
    ke_test = _read_json(workspace / SOURCE_PATH)
    units = build_turn_units(ke_test)
    extraction_dir = baseline_root / "model-extraction"
    batches = [
        _read_json(extraction_dir / "batch-a.json"),
        _read_json(extraction_dir / "batch-b.json"),
    ]
    merged = merge_model_graph_batches(batches)
    validate_model_graphs(units, merged)
    _write_json(extraction_dir / "combined.json", merged)

    dataset_root = materialize_keol_dataset(
        units,
        merged,
        baseline_root / "native-output",
        dataset_name,
    )

    keol_src = keol_root / "src"
    sys.path.insert(0, str(keol_src))
    try:
        from onto.builder import build_ontology
        from onto.validator import validate_ontology_output

        result = build_ontology(
            dataset_root,
            use_llm=False,
            validate=True,
            strict_validation=True,
        )
        validation = validate_ontology_output(dataset_root, write=True, strict=True)
    finally:
        sys.path.remove(str(keol_src))

    summary = {
        "schema_version": "keol_ke_test_run_v1",
        "source": SOURCE_PATH.as_posix(),
        "keol_commit": KEOL_COMMIT,
        "model_provider": merged["model_provider"],
        "dataset_root": str(dataset_root),
        "input": {
            "candidate_count": len(ke_test["candidates"]),
            "turn_count": len(units),
            "model_unit_count": len(merged["units"]),
            "node_count": sum(len(item["nodes"]) for item in merged["units"]),
            "edge_count": sum(len(item["edges"]) for item in merged["units"]),
        },
        "ontology": {
            "concept_count": len(result.concepts),
            "individual_count": len(result.individuals),
            "operator_count": len(result.operators),
            "assertion_count": len(result.assertions),
            "evidence_count": len(result.evidence),
        },
        "validation": {
            "ok": bool(validation.ok),
            "error_count": int(validation.error_count),
            "warning_count": int(validation.warning_count),
        },
    }
    _write_json(baseline_root / "run" / "KEOL-run.json", summary)
    return summary


def prepare_normalization_payloads(
    workspace: Path,
    keol_root: Path,
    *,
    dataset_name: str = "KE-test",
    batch_size: int = 40,
) -> list[Path]:
    baseline_root = workspace / BASELINE_ROOT
    dataset_root = baseline_root / "native-output" / dataset_name
    keol_src = keol_root / "src"
    sys.path.insert(0, str(keol_src))
    try:
        from onto.builder import build_ontology

        result = build_ontology(
            dataset_root,
            write=False,
            use_llm=False,
            validate=False,
        )
    finally:
        sys.path.remove(str(keol_src))
    return write_normalization_payloads(
        result,
        keol_root,
        baseline_root / "model-normalization",
        batch_size=batch_size,
    )


def apply_normalization_stage(
    workspace: Path,
    keol_root: Path,
    *,
    dataset_name: str = "KE-test",
) -> dict[str, Any]:
    baseline_root = workspace / BASELINE_ROOT
    dataset_root = baseline_root / "native-output" / dataset_name
    normalization_dir = baseline_root / "model-normalization"
    payload_paths = sorted(normalization_dir.glob("payload-*.json"))
    plan_paths = sorted(normalization_dir.glob("plan-*.json"))
    if len(payload_paths) != len(plan_paths):
        raise ValueError(
            f"normalization payload/plan counts differ: {len(payload_paths)} != {len(plan_paths)}"
        )

    keol_src = keol_root / "src"
    sys.path.insert(0, str(keol_src))
    try:
        from onto.agent_projection import build_agent_ontology
        from onto.builder import build_ontology
        from onto.store import save_ontology_result
        from onto.validator import validate_ontology_output

        result = build_ontology(dataset_root, write=False, use_llm=False, validate=False)
        batch_stats = apply_normalization_plan_files(
            result, keol_root, payload_paths, plan_paths
        )
        result.agent_ontology = build_agent_ontology(result)
        save_ontology_result(dataset_root, result)
        validation = validate_ontology_output(dataset_root, write=True, strict=True)
    finally:
        sys.path.remove(str(keol_src))

    summary_path = baseline_root / "run" / "KEOL-run.json"
    summary = _read_json(summary_path)
    summary["normalization"] = {
        "provider": "codex_subagent",
        "batch_count": len(batch_stats),
        "concept_update_count": sum(
            len(_read_json(path).get("concept_updates", [])) for path in plan_paths
        ),
        "operator_update_count": sum(
            len(_read_json(path).get("operator_updates", [])) for path in plan_paths
        ),
        "batches": batch_stats,
    }
    summary["validation"] = {
        "ok": bool(validation.ok),
        "error_count": int(validation.error_count),
        "warning_count": int(validation.warning_count),
    }
    _write_json(summary_path, summary)
    return summary


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[2]
    keol_root = Path(r"C:\Users\86137\Desktop\Haitun-agent\KEOL")
    if len(sys.argv) > 1 and sys.argv[1] == "prepare-normalization":
        paths = prepare_normalization_payloads(root, keol_root)
        print(json.dumps({"payload_count": len(paths), "paths": [str(path) for path in paths]}, ensure_ascii=False, indent=2))
    elif len(sys.argv) > 1 and sys.argv[1] == "apply-normalization":
        print(json.dumps(apply_normalization_stage(root, keol_root), ensure_ascii=False, indent=2))
    else:
        result = run_pipeline(root, keol_root)
        print(json.dumps(result, ensure_ascii=False, indent=2))
