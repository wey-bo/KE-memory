"""Parse the schema.org vocabulary from its released JSON-LD graph.

Fetched from the ``schemaorg/schemaorg`` GitHub repository rather than from schema.org,
because outbound HTTPS to schema.org times out on this host. The released JSON-LD under
``data/releases/<version>/`` is the same artifact the site publishes, and pinning it to a
repository commit gives a stronger provenance claim than a live fetch would.

The graph is flat: classes, properties and enumeration members are sibling nodes
distinguished by ``@type``. Enumeration members (e.g. ``schema:Paperback``, typed
``schema:BookFormatType``) are counted separately from classes because they are instances,
not types, and conflating them inflates any "class count" claim.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
import json
from pathlib import Path
from typing import cast

from ke_memory_demo.ontology_sources.models import (
    SchemaOrgSnapshot,
    SchemaOrgTerm,
    SourceAcquisition,
)

_CLASS_TYPE = "rdfs:Class"
_PROPERTY_TYPE = "rdf:Property"
_SAMPLE_LIMIT = 12
# Only classes are sampled, and only these, so the sample stays stable across releases
# instead of being whatever happens to sort first.
_SAMPLE_TERMS = frozenset(
    {
        "schema:Thing",
        "schema:Person",
        "schema:Organization",
        "schema:Place",
        "schema:Event",
        "schema:Action",
        "schema:CreativeWork",
        "schema:Product",
        "schema:Intangible",
        "schema:Article",
    }
)


class SchemaOrgParseError(ValueError):
    """The schema.org JSON-LD did not contain a usable ``@graph``."""


def load_schemaorg(
    document: Path, acquisition: SourceAcquisition, release: str
) -> SchemaOrgSnapshot:
    """Parse the vocabulary graph and return a compact, counted snapshot."""
    raw = json.loads(document.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise SchemaOrgParseError(f"{document} is not a JSON-LD object")
    graph = cast(dict[str, object], raw).get("@graph")
    if not isinstance(graph, list):
        raise SchemaOrgParseError(f"{document} has no @graph array")
    nodes = cast(list[object], graph)

    classes = 0
    properties = 0
    enumeration_members = 0
    sample: dict[str, SchemaOrgTerm] = {}

    for node in nodes:
        if not isinstance(node, dict):
            continue
        entry = cast(Mapping[str, object], node)
        term_id = entry.get("@id")
        types = _as_tuple(entry.get("@type"))
        if not isinstance(term_id, str) or not types:
            continue
        if _CLASS_TYPE in types:
            classes += 1
            if term_id in _SAMPLE_TERMS:
                sample[term_id] = _build_term(entry, term_id, _CLASS_TYPE)
        elif _PROPERTY_TYPE in types:
            properties += 1
        else:
            # Anything else typed by a schema.org class is an enumeration member.
            enumeration_members += 1

    if not classes or not properties:
        raise SchemaOrgParseError(
            f"{document} parsed to {classes} classes and {properties} properties"
        )

    return SchemaOrgSnapshot(
        release=release,
        acquisition=acquisition,
        graph_node_count=len(nodes),
        class_count=classes,
        property_count=properties,
        enumeration_member_count=enumeration_members,
        sample=tuple(sample[key] for key in sorted(sample)),
    )


def _build_term(
    entry: Mapping[str, object], term_id: str, term_type: str
) -> SchemaOrgTerm:
    label = entry.get("rdfs:label")
    comment = entry.get("rdfs:comment")
    supertypes = tuple(
        reference
        for reference in _references(entry.get("rdfs:subClassOf"))
        # Cross-vocabulary parents (rdfs:Resource, owl:Thing) are dropped so the sample
        # shows the schema.org hierarchy rather than its RDF framing.
        if reference.startswith("schema:")
    )
    return SchemaOrgTerm(
        term_id=term_id,
        label=label if isinstance(label, str) and label else term_id.removeprefix("schema:"),
        term_type=term_type,
        supertypes=supertypes,
        comment=comment if isinstance(comment, str) else "",
    )


def _as_tuple(value: object) -> tuple[str, ...]:
    """JSON-LD allows a single value where a list is permitted; normalise both."""
    if isinstance(value, str):
        return (value,)
    if isinstance(value, list):
        return tuple(item for item in cast(list[object], value) if isinstance(item, str))
    return ()


def _references(value: object) -> Iterable[str]:
    """Yield ``@id`` targets from a property that may be a node, a list, or absent."""
    candidates: list[object] = (
        list(cast(list[object], value)) if isinstance(value, list) else [value]
    )
    for candidate in candidates:
        if isinstance(candidate, dict):
            target = cast(Mapping[str, object], candidate).get("@id")
            if isinstance(target, str):
                yield target
        elif isinstance(candidate, str):
            yield candidate
