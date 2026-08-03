"""Read the frozen mapping set, the two ontology generations and the frozen gold back from disk.

The loaders exist so the tests check the *artifacts* rather than the in-memory objects that
produced them. A test that only exercised ``build_annotation_gold`` would pass while the written
JSON was stale or truncated, and the written JSON is what any later scoring run consumes.

Only the ontology units are read. Nothing here opens a mapper module, a mapper artifact, the
previous round's gold or the benchmark plan, and there is no function that could: the annotation
line's independence is a property of what this file can reach.

v2 items nest the definition under an ``item`` key and v3's additions do not, so id extraction is
shape-tolerant on purpose. Parsing the additions through the v2 freeze models is not an option --
they carry their own field set (``evidence_family``, ``admitted_on``) that ``extra="forbid"`` on
the v2 models rejects, and loosening those models to accommodate a reader would be the wrong
direction of change.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Final, cast

from pydantic import TypeAdapter

from ke_memory_demo.core.json import JsonObject

from .models import AnnotationGold

SET_PATH: Final[Path] = Path("artifacts/mapper-v3-validation/fresh-mapping-set.json")
GOLD_PATH: Final[Path] = Path("artifacts/mapper-v3-validation/annotation-gold.json")
ONTOLOGY_V2_DIR: Final[Path] = Path("artifacts/ontology-v2")
ONTOLOGY_V3_DIR: Final[Path] = Path("artifacts/ontology-v3")

_GOLD_ADAPTER: Final[TypeAdapter[AnnotationGold]] = TypeAdapter(AnnotationGold)


def _read_json(path: Path) -> JsonObject:
    payload: object = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise TypeError(f"{path} does not contain a JSON object")
    # isinstance cannot narrow a generic's parameters, so the cast carries the guarantee the
    # check above established.
    return cast(JsonObject, payload)


def load_mapping_set(root: Path) -> JsonObject:
    """The frozen 160-expression set, exactly as written."""
    return _read_json(root / SET_PATH)


def mapping_set_expression_ids(root: Path) -> frozenset[str]:
    payload = load_mapping_set(root)
    expressions = payload["expressions"]
    if not isinstance(expressions, list):
        raise TypeError("the set's 'expressions' field is not a list")
    ids: set[str] = set()
    for entry in expressions:
        if not isinstance(entry, dict):
            raise TypeError("a set expression is not an object")
        identifier = entry["expression_id"]
        if not isinstance(identifier, str):
            raise TypeError("an expression_id is not a string")
        ids.add(identifier)
    return frozenset(ids)


def mapping_set_digest(root: Path) -> str:
    recorded = load_mapping_set(root)["set_sha256"]
    if not isinstance(recorded, str):
        raise TypeError("set_sha256 is not a string")
    return recorded


def _item_ids(payload: JsonObject) -> frozenset[str]:
    items = payload["items"]
    if not isinstance(items, list):
        raise TypeError("an ontology unit's 'items' field is not a list")
    ids: set[str] = set()
    for entry in items:
        if not isinstance(entry, dict):
            raise TypeError("an ontology item is not an object")
        inner = entry.get("item", entry)
        if not isinstance(inner, dict):
            raise TypeError("an ontology item's definition is not an object")
        identifier = inner["id"]
        if not isinstance(identifier, str):
            raise TypeError("an ontology item id is not a string")
        ids.add(identifier)
    return frozenset(ids)


def _role_ids(payload: JsonObject) -> frozenset[str]:
    """The roles a unit declares outside its item list, as v3 does for its three new roles."""
    roles = payload.get("new_roles")
    if roles is None:
        return frozenset()
    if not isinstance(roles, list):
        raise TypeError("'new_roles' is not a list")
    ids: set[str] = set()
    for entry in roles:
        if not isinstance(entry, dict):
            raise TypeError("a role entry is not an object")
        identifier = entry["id"]
        if not isinstance(identifier, str):
            raise TypeError("a role id is not a string")
        ids.add(identifier)
    return frozenset(ids)


def load_v2_ids(root: Path) -> frozenset[str]:
    directory = root / ONTOLOGY_V2_DIR
    return _item_ids(_read_json(directory / "o_l1.json")) | _item_ids(
        _read_json(directory / "o_l2.json")
    )


def load_v3_added_ids(root: Path) -> frozenset[str]:
    directory = root / ONTOLOGY_V3_DIR
    l1 = _read_json(directory / "o_l1_additions.json")
    l2 = _read_json(directory / "o_l2_additions.json")
    return _item_ids(l1) | _role_ids(l1) | _item_ids(l2) | _role_ids(l2)


def load_combined_ontology_ids(root: Path) -> frozenset[str]:
    """The union a label may name: the v2 base plus the v3 additions and their new roles."""
    return load_v2_ids(root) | load_v3_added_ids(root)


def load_gold(root: Path) -> AnnotationGold:
    """The written gold, validated back through its own model."""
    payload = _read_json(root / GOLD_PATH)
    return _GOLD_ADAPTER.validate_python(
        {
            "annotated_set_sha256": payload["annotated_set_sha256"],
            "annotated_against_ontology": payload["annotated_against_ontology"],
            "records": payload["records"],
        }
    )


def load_gold_digest(root: Path) -> str:
    """The digest the artifact claims for itself, as opposed to the one recomputed from it."""
    recorded = _read_json(root / GOLD_PATH)["gold_sha256"]
    if not isinstance(recorded, str):
        raise TypeError("gold_sha256 is not a string")
    return recorded
