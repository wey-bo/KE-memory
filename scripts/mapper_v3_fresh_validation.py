"""Run the mapper v3 fresh-set validation exactly once, and record what produced the result.

The round's rule is that this runs a single time. Whatever the numbers are, they stand: a low score
is a result, not a reason to adjust the mapper and try again. Re-execution is permitted only when
nothing semantic was produced -- an interpreter crash, a missing file -- and only when every input
digest is byte-identical to what the manifest below recorded.

So the manifest is written *before* the mapper is called, and the report is written after, with the
manifest's own digest embedded in it. That ordering is what makes the claim checkable rather than
asserted: a report naming a manifest digest could not have been produced by a run whose inputs were
changed afterwards.

Isolation at this point is a property of the call graph, not of intent. This script is the only
place where the gold, the mapper and the scorer are in scope together. The mapper receives the
expression id, the speaker and the text; the gold is not passed to it, and the scorer sees the
mapper's results and the gold but never the mapper itself.
"""

from __future__ import annotations

import hashlib
import json
import platform
import sys
from pathlib import Path
from typing import Any, Final, cast

from ke_memory_demo.core.json import canonical_json
from ke_memory_demo.mapper_v3.mapper_v3 import ExpressionInput, MapperV3
from ke_memory_demo.mapper_v3_scoring.runner import build_report_artifact
from ke_memory_demo.mapper_v3_validation.loader import (
    load_combined_ontology_ids,
    load_gold,
    load_mapping_set,
    mapping_set_digest,
)

ROOT: Final[Path] = Path(".")
V2_DIR: Final[Path] = ROOT / "artifacts" / "ontology-v2"
V3_DIR: Final[Path] = ROOT / "artifacts" / "ontology-v3"
OUT_DIR: Final[Path] = ROOT / "artifacts" / "mapper-v3-validation"
MANIFEST_PATH: Final[Path] = OUT_DIR / "pre-run-manifest.json"
REPORT_PATH: Final[Path] = OUT_DIR / "validation-report.json"

# The inputs this round froze. Checked, not trusted: if any digest on disk has moved, the run stops
# before the mapper is constructed.
EXPECTED: Final[dict[str, str]] = {
    "fresh_set": "b576db052cb158364dde3261bfb6d10d150b4874ee1dd524efc91799793d42db",
    "gold_model_digest": "c636fb18925070b9e7ed92236ef802da51fc5e184667b5046e2bdfedc162b33d",
    "mapper_freeze": "f096094d789361314611c2bf58b887cb5338b6f78c8e1c2039f1f745aa2df219",
}


def _unit_digest(path: Path) -> str:
    payload: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return str(payload["freeze"]["sha256"])


def _artifact_digest(path: Path, field: str) -> str:
    payload: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return str(payload[field])


def _refuse(reason: str) -> None:
    raise SystemExit(
        f"refusing to run: {reason}. This validation may be executed once, so it must not run "
        "against inputs that differ from the frozen ones"
    )


def main() -> int:
    if REPORT_PATH.exists():
        _refuse(
            f"{REPORT_PATH} already exists. The round permits one execution; re-running would "
            "overwrite an immutable result. Delete it deliberately only for a pure execution "
            "failure that produced no semantic output"
        )

    gold = load_gold(ROOT)
    set_digest = mapping_set_digest(ROOT)
    mapper = MapperV3(v2_dir=V2_DIR, v3_dir=V3_DIR)

    if set_digest != EXPECTED["fresh_set"]:
        _refuse(f"the fresh set digest is {set_digest}, not the frozen {EXPECTED['fresh_set']}")
    if gold.digest != EXPECTED["gold_model_digest"]:
        _refuse(f"the gold digest is {gold.digest}, not the frozen {EXPECTED['gold_model_digest']}")
    if mapper.freeze_hash() != EXPECTED["mapper_freeze"]:
        _refuse(
            f"the mapper freeze hash is {mapper.freeze_hash()}, not the frozen "
            f"{EXPECTED['mapper_freeze']}"
        )
    if gold.annotated_set_sha256 != set_digest:
        _refuse("the gold was annotated against a different draw of the set")

    manifest = _build_manifest(gold, set_digest, mapper)
    manifest["manifest_sha256"] = hashlib.sha256(canonical_json(manifest)).hexdigest()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=1, sort_keys=True), encoding="utf-8")
    print(f"pre-run manifest: {manifest['manifest_sha256']}")

    results = _run_mapper(mapper)
    artifact = build_report_artifact(gold, results, load_combined_ontology_ids(ROOT))
    artifact["run_standing"] = "single_execution_immutable_result"
    artifact["pre_run_manifest_sha256"] = manifest["manifest_sha256"]
    artifact["not_a_benchmark_claim"] = (
        "a mapping-quality measurement over 160 expressions. It is not a benchmark result and "
        "confers no production or Stage 4 qualification; that decision is taken separately from "
        "this artifact"
    )
    REPORT_PATH.write_text(json.dumps(artifact, indent=1, sort_keys=True), encoding="utf-8")

    _print_summary(artifact)
    print(f"report: {REPORT_PATH}")
    return 0


def _build_manifest(gold: Any, set_digest: str, mapper: MapperV3) -> dict[str, Any]:
    return {
        "artifact": "mapper v3 fresh validation pre-run manifest",
        "written": "before the mapper was called, so the report can name this manifest's digest",
        "execution_policy": {
            "runs_permitted": 1,
            "low_score_is_a_result": (
                "a poor number is the finding. Adjusting the mapper and re-running would measure a "
                "mapper fitted to this set"
            ),
            "re_execution_allowed_only_if": (
                "no semantic output was produced and every digest here is byte-identical"
            ),
        },
        "inputs": {
            "fresh_set_sha256": set_digest,
            "fresh_set_expressions": len(_expression_rows()),
            "gold_model_digest": gold.digest,
            "gold_artifact_sha256": _artifact_digest(
                OUT_DIR / "annotation-gold.json", "gold_sha256"
            ),
            "gold_counts_by_outcome": gold.counts_by_outcome(),
            "mapper_freeze_hash": mapper.freeze_hash(),
            "mapper_artifact_sha256": _artifact_digest(
                OUT_DIR / "mapper-freeze.json", "artifact_sha256"
            ),
            "ontology": {
                "o_v2_l1": _unit_digest(V2_DIR / "o_l1.json"),
                "o_v2_l2": _unit_digest(V2_DIR / "o_l2.json"),
                "o_v3_l1": _unit_digest(V3_DIR / "o_l1_additions.json"),
                "o_v3_l2": _unit_digest(V3_DIR / "o_l2_additions.json"),
                "m_l1_to_l2_v3": _unit_digest(V3_DIR / "m_l1_to_l2_additions.json"),
            },
        },
        "commits": {
            "baseline": "796f47c",
            "scorer": "d430f5b",
            "gold": "6f35ed6",
            "mapper_freeze": "17a7887",
        },
        "known_limits": {
            "true_ambiguity_abstention": (
                "the gold holds zero ambiguous records, so this metric must report unavailable. No "
                "record was added afterwards to give it a denominator"
            ),
            "annotator_independence": (
                "procedural declaration, not artifact proof: both halves of the gold were written "
                "while mapper v3 already existed in the tree. Import isolation in both directions "
                "is what the architecture gate does establish"
            ),
            "ontology_gaps_accounted": (
                "three v2 gaps (habit derivation bound to media consumption, kinship lacking "
                "collateral descent, circumstance unable to say medical) and one unlicensed v3 "
                "addition (l2:abstraction.value_commitment) are recorded in the gold artifact and "
                "were not repaired; no ontology byte changed for this run"
            ),
        },
        "environment": {
            "python": sys.version.split()[0],
            "platform": platform.platform(),
        },
    }


def _expression_rows() -> list[dict[str, Any]]:
    payload = load_mapping_set(ROOT)
    rows = payload["expressions"]
    if not isinstance(rows, list):
        raise SystemExit("the set's 'expressions' field is not a list")
    typed: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            raise SystemExit("a set expression is not an object")
        typed.append(row)
    return typed


def _run_mapper(mapper: MapperV3) -> list[Any]:
    """Map every expression. The gold is not in scope inside this function."""
    results: list[Any] = []
    for row in _expression_rows():
        request = ExpressionInput(
            expression_id=str(row["expression_id"]),
            speaker=str(row["speaker"]),
            text=str(row["text"]),
        )
        results.append(mapper.map_expression(request))
    return results


def _print_summary(artifact: dict[str, Any]) -> None:
    report_value: object = artifact["report"]
    if not isinstance(report_value, dict):
        return
    report = cast("dict[str, object]", report_value)

    def nested(container: dict[str, object], key: str) -> dict[str, object] | None:
        value = container.get(key)
        if not isinstance(value, dict):
            return None
        return cast("dict[str, object]", value)

    def show(label: str, metric: dict[str, object] | None) -> None:
        if metric is None:
            return
        if metric.get("availability") == "unavailable":
            reason = str(metric.get("unavailable_reason", ""))
            print(f"  {label}: unavailable ({reason[:70]})")
            return
        print(
            f"  {label}: {metric.get('value')} "
            f"({metric.get('numerator')}/{metric.get('denominator')}, "
            f"completed {metric.get('completed')})"
        )

    print(f"expressions scored: {report.get('total_mapping_results')}")
    show("ontology_coverage", nested(report, "ontology_coverage"))

    recall = nested(report, "candidate_recall")
    if recall is not None:
        show("candidate_recall.micro", nested(recall, "micro"))
        show("candidate_recall.macro", nested(recall, "macro"))

    show("ranking_or_sense", nested(report, "ranking_or_sense_accuracy"))

    no_map = nested(report, "no_map_behaviour")
    if no_map is not None:
        show("correct_abstention", nested(no_map, "correct_abstention"))
        show("missed_content", nested(no_map, "missed_content"))

    multi = nested(report, "multi_label_selection")
    if multi is not None:
        show("multi_label_selection", nested(multi, "multi_label_selection"))
        show("incomplete_multi_label", nested(multi, "incomplete_multi_label_selection"))

    show("critical_false_mapping", nested(report, "critical_false_mapping"))
    show("true_ambiguity_abstention", nested(report, "true_ambiguity_abstention"))


if __name__ == "__main__":
    raise SystemExit(main())
