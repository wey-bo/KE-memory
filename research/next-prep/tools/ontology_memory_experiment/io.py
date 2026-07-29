from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from .models import (
    DistractorDocument,
    GoldDocument,
    OracleQueryPlanDocument,
    OracleRepresentationDocument,
    SourceDocument,
)


def _plain(value: Any) -> Any:
    return value.model_dump(mode="json") if isinstance(value, BaseModel) else value


def canonical_json_bytes(value: Any) -> bytes:
    return (json.dumps(_plain(value), ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json_immutable(path: Path, value: Any) -> None:
    content = canonical_json_bytes(value)
    if path.exists():
        if path.read_bytes() != content:
            raise FileExistsError(f"immutable artifact differs: {path}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def write_manifest(path: Path, files: dict[str, Path]) -> dict[str, Any]:
    manifest = {
        "schema_version": "ontology-memory-gold-manifest-v1",
        "files": {
            name: {"path": file.as_posix(), "sha256": sha256_file(file)}
            for name, file in sorted(files.items())
        },
    }
    write_json_immutable(path, manifest)
    return manifest


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def load_source_document(path: Path) -> SourceDocument:
    return SourceDocument.model_validate(_load_json(path))


def load_gold_document(path: Path) -> GoldDocument:
    return GoldDocument.model_validate(_load_json(path))


def load_distractor_document(path: Path) -> DistractorDocument:
    return DistractorDocument.model_validate(_load_json(path))


def load_oracle_representation_document(path: Path) -> OracleRepresentationDocument:
    return OracleRepresentationDocument.model_validate(_load_json(path))


def load_oracle_query_plan_document(path: Path) -> OracleQueryPlanDocument:
    return OracleQueryPlanDocument.model_validate(_load_json(path))


def validate_document_links(source: SourceDocument, gold: GoldDocument, distractors: DistractorDocument) -> None:
    source_by_id = {scenario.scenario_id: scenario for scenario in source.scenarios}
    if len(source_by_id) != len(source.scenarios):
        raise ValueError("source scenario IDs must be unique")
    if {scenario.scenario_id for scenario in gold.scenarios} != set(source_by_id):
        raise ValueError("source and gold scenario IDs must match exactly")
    for gold_scenario in gold.scenarios:
        source_turn_ids = {turn.turn_id for turn in source_by_id[gold_scenario.scenario_id].turns}
        if not set(gold_scenario.required_evidence_turn_ids) <= source_turn_ids:
            raise ValueError(f"unknown evidence for {gold_scenario.scenario_id}")
        if not set(gold_scenario.hard_negative_turn_ids) <= source_turn_ids:
            raise ValueError(f"unknown hard negative for {gold_scenario.scenario_id}")
    if any(record.scenario_id not in source_by_id for record in distractors.records):
        raise ValueError("distractors must belong to source scenarios")
