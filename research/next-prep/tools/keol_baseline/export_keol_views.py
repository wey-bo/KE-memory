from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .keol_ke_test_adapter import build_turn_units


SOURCE_PATH = Path("data/gold-candidates/KE-test.json")
BASELINE_ROOT = Path("artifacts/keol-baseline")


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _quoted(value: str) -> str:
    return json.dumps(str(value), ensure_ascii=False)


def render_keol_term(
    term: dict[str, Any],
    *,
    operators: dict[str, str],
    individuals: dict[str, str],
    concepts: dict[str, str],
) -> str:
    term_type = term.get("term_type")
    term_id = term.get("id")
    if term_type == "individual":
        return f"Individual({_quoted(individuals.get(term_id, term_id or 'unknown'))})"
    if term_type == "concept":
        return f"Concept({_quoted(concepts.get(term_id, term_id or 'unknown'))})"
    if term_type == "operator":
        return f"Operator({_quoted(operators.get(term_id, term_id or 'unknown'))})"
    if term_type == "assertion":
        return f"Assertion({_quoted(term_id or 'unknown')})"
    if term_type == "operator_application":
        name = operators.get(term.get("operator_id"), term.get("operator_id") or "unknown")
        args = [
            render_keol_term(
                argument.get("term", {}),
                operators=operators,
                individuals=individuals,
                concepts=concepts,
            )
            for argument in term.get("arguments", [])
        ]
        return f"{name}({','.join(args)})"
    return f"Term({_quoted(term_id or term_type or 'unknown')})"


def _unit_id_from_source_file(source_file: str) -> str | None:
    match = re.search(r"([^/\\]+)\.txt$", source_file or "")
    return match.group(1) if match else None


def build_assertion_unit_index(
    assertions: list[dict[str, Any]], evidence: list[dict[str, Any]]
) -> dict[str, list[str]]:
    evidence_by_id = {item.get("id"): item for item in evidence}
    index: dict[str, list[str]] = {}
    for assertion in assertions:
        assertion_id = assertion.get("id")
        unit_ids = {
            _unit_id_from_source_file(evidence_by_id.get(evidence_id, {}).get("source_file", ""))
            for evidence_id in assertion.get("evidence_ids", [])
        }
        for unit_id in sorted(item for item in unit_ids if item):
            index.setdefault(unit_id, []).append(assertion_id)
    for assertion_ids in index.values():
        assertion_ids.sort()
    return index


def export_views(workspace: Path, *, dataset_name: str = "KE-test") -> dict[str, Any]:
    baseline_root = workspace / BASELINE_ROOT
    dataset_root = baseline_root / "native-output" / dataset_name
    onto_root = dataset_root / "onto"
    ke_test = _read_json(workspace / SOURCE_PATH)
    units = build_turn_units(ke_test)
    graphs = _read_json(baseline_root / "model-extraction" / "combined.json")
    graph_by_unit = {item["unit_id"]: item for item in graphs["units"]}

    file_names = {
        "concepts": "concepts.json",
        "individuals": "individuals.json",
        "operators": "operators.json",
        "assertions": "assertions.json",
        "evidence": "evidence.json",
        "workflow_runs": "workflow_runs.json",
    }
    native = {key: _read_json(onto_root / filename) for key, filename in file_names.items()}
    concepts = {item["id"]: item["name"] for item in native["concepts"]}
    individuals = {item["id"]: item["name"] for item in native["individuals"]}
    operators = {item["id"]: item["name"] for item in native["operators"]}
    assertion_by_id = {item["id"]: item for item in native["assertions"]}
    assertion_index = build_assertion_unit_index(native["assertions"], native["evidence"])

    agent = {}
    agent_root = onto_root / "agent"
    for name in ("concepts", "constants", "operators", "facts", "rules", "requests", "evidence", "workflow_runs", "symbol_map", "metadata"):
        path = agent_root / f"{name}.json"
        if path.exists():
            agent[name] = _read_json(path)
    action = {}
    action_root = onto_root / "action"
    for name in ("skills", "tools", "action_concepts", "action_operators", "actions", "metadata"):
        path = action_root / f"{name}.json"
        if path.exists():
            action[name] = _read_json(path)

    ontology_view = {
        "schema_version": "keol_ontology_view_v1",
        "keol_commit": graphs["keol_commit"],
        "source": SOURCE_PATH.as_posix(),
        **native,
        "agent": agent,
        "action": action,
        "native_root": str(onto_root),
    }
    views_root = baseline_root / "views"
    _write_json(views_root / "KE-ontology.json", ontology_view)

    extraction_units = []
    for unit in units:
        unit_id = unit["unit_id"]
        assertion_ids = assertion_index.get(unit_id, [])
        extraction_units.append(
            {
                **unit,
                "graph": graph_by_unit[unit_id],
                "assertion_ids": assertion_ids,
                "assertions": [assertion_by_id[item] for item in assertion_ids],
            }
        )
    extraction_view = {
        "schema_version": "keol_extraction_view_v1",
        "keol_commit": graphs["keol_commit"],
        "source": SOURCE_PATH.as_posix(),
        "model_provider": graphs.get("model_provider", ""),
        "units": extraction_units,
        "native_onto_root": str(onto_root),
        "summary": {
            "candidate_count": len(ke_test["candidates"]),
            "turn_count": len(units),
            "model_node_count": sum(len(item["nodes"]) for item in graphs["units"]),
            "model_edge_count": sum(len(item["edges"]) for item in graphs["units"]),
            "assertion_count": len(native["assertions"]),
            "evidence_count": len(native["evidence"]),
            "assertion_unit_links": sum(len(item) for item in assertion_index.values()),
        },
    }
    _write_json(views_root / "KE-extraction.json", extraction_view)

    lines: list[str] = []
    for candidate in ke_test["candidates"]:
        candidate_id = candidate["id"]
        candidate_units = [
            unit for unit in units if unit["candidate_id"] == candidate_id
        ]
        candidate_assertions = [
            assertion_id
            for unit in candidate_units
            for assertion_id in assertion_index.get(unit["unit_id"], [])
        ]
        if not candidate_assertions:
            continue
        lines.append(f"对话id: {candidate_id}")
        ke_index = 1
        seen: set[str] = set()
        for unit in candidate_units:
            assertion_ids = assertion_index.get(unit["unit_id"], [])
            if not assertion_ids:
                continue
            lines.append(f"轮次: {unit['turn_index']}")
            for assertion_id in assertion_ids:
                if assertion_id in seen:
                    continue
                seen.add(assertion_id)
                assertion = assertion_by_id[assertion_id]
                lhs = render_keol_term(
                    assertion["lhs"],
                    operators=operators,
                    individuals=individuals,
                    concepts=concepts,
                )
                rhs = render_keol_term(
                    assertion["rhs"],
                    operators=operators,
                    individuals=individuals,
                    concepts=concepts,
                )
                lines.append(f"KE{ke_index}: {lhs}={rhs}")
                ke_index += 1
        lines.append("")
    (views_root / "KE.txt").write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return extraction_view["summary"]


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[2]
    print(json.dumps(export_views(root), ensure_ascii=False, indent=2))
