"""schema.org 30.0 term records, read from the JSON-LD graph.

Three term kinds are distinguished, because `@type` is not a single value: nodes are
`rdfs:Class`, `rdf:Property`, or an enumeration member typed by its own enumeration
(`schema:Paperback` is a `schema:BookFormatType`). The graph holds 1,010 classes, 1,676
properties and 533 enumeration members.

`rdfs:label` and `rdfs:comment` are usually strings but occasionally language-tagged
objects (`{"@language": "en", "@value": "archiveHeld"}`) -- 7 of each. Both shapes are
read; assuming the string form would drop those terms.

schema.org carries no sense or roleset identity, and the profile's conditional matrix
forbids both for `schema_org`, so `term_id` is the graph's `@id` and serves only as a
provenance locator.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any, cast

from memory_assertion_v1.sources.records import (
    SchemaOrgTermRecord,
    SchemaOrgTermKind,
    SourceLocation,
)

CLASS_TYPE = "rdfs:Class"
PROPERTY_TYPE = "rdf:Property"


class SchemaOrgParseError(ValueError):
    """The document is not a schema.org JSON-LD graph."""


def _types(node: dict[str, Any]) -> tuple[str, ...]:
    raw = node.get("@type")
    if isinstance(raw, str):
        return (raw,)
    if isinstance(raw, list):
        return tuple(str(item) for item in cast("list[Any]", raw))
    return ()


def _text(value: Any) -> str:
    """Read a possibly language-tagged literal."""
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        tagged = cast("dict[str, Any]", value).get("@value")
        if isinstance(tagged, str):
            return tagged
    return ""


def _references(value: Any) -> tuple[str, ...]:
    """Read `@id` references that may be a single object or a list of them."""
    items: list[Any] = []
    if isinstance(value, list):
        items = list(cast("list[Any]", value))
    elif value is not None:
        items = [value]
    found: list[str] = []
    for item in items:
        if isinstance(item, dict):
            reference = cast("dict[str, Any]", item).get("@id")
            if isinstance(reference, str) and reference:
                found.append(reference)
        elif isinstance(item, str) and item:
            found.append(item)
    return tuple(found)


def _term_kind(types: tuple[str, ...]) -> SchemaOrgTermKind:
    if CLASS_TYPE in types:
        return "class"
    if PROPERTY_TYPE in types:
        return "property"
    return "enumeration_member"


def parse_graph(payload: bytes, location: SourceLocation) -> tuple[SchemaOrgTermRecord, ...]:
    """Parse every named term in the graph.

    Nodes without an `@id` or without a label are skipped rather than raising: the graph
    legitimately contains structural nodes that name no term, and treating those as
    corruption would make a valid release unreadable.
    """
    document = cast("dict[str, Any]", json.loads(payload.decode("utf-8")))
    graph = document.get("@graph")
    if not isinstance(graph, list):
        raise SchemaOrgParseError("document has no @graph array")

    records: list[SchemaOrgTermRecord] = []
    for node in cast("list[Any]", graph):
        if not isinstance(node, dict):
            continue
        typed = cast("dict[str, Any]", node)
        term_id = typed.get("@id")
        label = _text(typed.get("rdfs:label"))
        if not isinstance(term_id, str) or not term_id or not label:
            continue
        types = _types(typed)
        kind = _term_kind(types)
        parents = (
            _references(typed.get("rdfs:subClassOf"))
            if kind == "class"
            else _references(typed.get("rdfs:subPropertyOf"))
            if kind == "property"
            else ()
        )
        records.append(
            SchemaOrgTermRecord(
                location=location,
                term_id=term_id,
                label=label,
                term_kind=kind,
                comment=_text(typed.get("rdfs:comment")),
                parents=parents,
            )
        )
    return tuple(records)


def iter_term_records(
    document: Path, artifact_sha256: str
) -> Iterator[SchemaOrgTermRecord]:
    """Read every term from the JSON-LD file."""
    location = SourceLocation(
        artifact_sha256=artifact_sha256, member_path=document.name
    )
    yield from parse_graph(document.read_bytes(), location)
