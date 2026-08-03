"""Read the frozen sample, the frozen ontology and the frozen gold back from disk.

The loaders exist so the tests check the *artifacts* rather than the in-memory objects that
produced them. A test that only exercises ``build_annotation_gold`` would pass while the written
JSON was stale or truncated, and the written JSON is what any later scoring run consumes.

Only the three ontology units are read. Nothing here opens a mapper module, a mapper artifact or
the benchmark plan, and there is no function that could: the annotation line's independence is a
property of what this file can reach.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Final, cast

from pydantic import TypeAdapter

from ke_memory_demo.core.json import JsonObject
from ke_memory_demo.ontology_v2.models import L1Freeze, L2Freeze, MappingFreeze

from .models import AnnotationGold

SAMPLE_PATH: Final[Path] = Path("artifacts/mapper-v2-validation/natural-expression-sample.json")
GOLD_PATH: Final[Path] = Path("artifacts/mapper-v2-validation/annotation-gold.json")
ONTOLOGY_DIR: Final[Path] = Path("artifacts/ontology-v2")

_GOLD_ADAPTER: Final[TypeAdapter[AnnotationGold]] = TypeAdapter(AnnotationGold)


def _read_json(path: Path) -> JsonObject:
    payload: object = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise TypeError(f"{path} does not contain a JSON object")
    # isinstance cannot narrow the parameters of a generic, so the cast is what carries the
    # guarantee the check above established.
    return cast(JsonObject, payload)


def load_sample(root: Path) -> JsonObject:
    """The frozen expression sample, exactly as written."""
    return _read_json(root / SAMPLE_PATH)


def sample_expression_ids(root: Path) -> frozenset[str]:
    sample = load_sample(root)
    expressions = sample["expressions"]
    if not isinstance(expressions, list):
        raise TypeError("the sample's 'expressions' field is not a list")
    ids: set[str] = set()
    for entry in expressions:
        if not isinstance(entry, dict):
            raise TypeError("a sample expression is not an object")
        identifier = entry["expression_id"]
        if not isinstance(identifier, str):
            raise TypeError("an expression_id is not a string")
        ids.add(identifier)
    return frozenset(ids)


def load_ontology_ids(root: Path) -> frozenset[str]:
    """Every id the two layers define, which is the only set a label may name.

    The units are parsed through their own freeze models rather than read as loose JSON, so a
    label is checked against an ontology that still satisfies its own validators. Reading the
    ids out of raw dicts would let a corrupted unit certify a label.
    """
    directory = root / ONTOLOGY_DIR
    l1 = L1Freeze.model_validate(_strip_freeze(_read_json(directory / "o_l1.json")))
    l2 = L2Freeze.model_validate(_strip_freeze(_read_json(directory / "o_l2.json")))
    mapping = MappingFreeze.model_validate(_strip_freeze(_read_json(directory / "m_l1_to_l2.json")))
    mapping.validate_against(l1, l2)
    return l1.item_ids | l2.item_ids


def _strip_freeze(payload: JsonObject) -> JsonObject:
    """Drop the artifact's ``freeze`` block, which is metadata about the unit, not the unit.

    The freeze block records the digest and the hash scope. It is written alongside the unit and
    is deliberately excluded from the hashed model, so it must come off before validation or
    ``extra="forbid"`` rejects the file the ontology build itself produced.
    """
    return {key: value for key, value in payload.items() if key != "freeze"}


def load_gold(root: Path) -> AnnotationGold:
    """The written gold, validated back through its own model."""
    payload = _read_json(root / GOLD_PATH)
    records = payload["records"]
    return _GOLD_ADAPTER.validate_python(
        {
            "sample_sha256": payload["sample_sha256"],
            "annotated_against_ontology": payload["annotated_against_ontology"],
            "records": records,
        }
    )


def load_gold_digest(root: Path) -> str:
    """The digest the artifact claims for itself, as opposed to the one recomputed from it."""
    recorded = _read_json(root / GOLD_PATH)["gold_sha256"]
    if not isinstance(recorded, str):
        raise TypeError("gold_sha256 is not a string")
    return recorded
