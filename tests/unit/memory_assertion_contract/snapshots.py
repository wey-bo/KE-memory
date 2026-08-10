"""Snapshot fixtures for the validator tests.

Two snapshots, for two different reasons.

`shipped_snapshot()` reads the conformance fixture from the spec package: 13 Concepts and
4 Operators that the specification itself commits to. It is the positive baseline.

`minimal_snapshot()` is built here, independently, and is the more important of the two.
The conformance harness in `spec/` reaches its input through a function that reads that one
fixture path, so its checks can only ever describe that snapshot. A validator tested only
against the shipped fixture could inherit the same blindness without anyone noticing, so
every rule is also exercised against a snapshot the fixture had no part in.

Mutation helpers deep-copy before editing. A test that mutated shared state would make the
next test's result depend on execution order.
"""

from __future__ import annotations

import copy
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

REPO_ROOT = Path(__file__).resolve().parents[3]
FIXTURE = REPO_ROOT / "spec/memory-assertion-v1/fixtures/ontology-snapshot-example"

BOOLEAN_CODEC = "ke-literal:boolean/v1"

# Minimal snapshot ids. Hash-shaped because the profile requires it, and distinct from the
# shipped fixture's ids so a test cannot accidentally pass by reaching the wrong snapshot.
ONTOLOGY_ID = "ontology_1111aaaa2222"
THING_ID = "concept_aaaa00000001"
PERSON_ID = "concept_aaaa00000002"
ROBOT_ID = "concept_aaaa00000003"
PROPOSITION_ID = "concept_aaaa00000004"
BOOLEAN_ID = "concept_aaaa00000005"
KNOWS_ID = "operator_bbbb00000001"
BELIEVES_ID = "operator_bbbb00000002"


def shipped_snapshot() -> list[dict[str, Any]]:
    """The conformance fixture's shards, in manifest order."""
    manifest = cast(
        "dict[str, Any]",
        json.loads((FIXTURE / "snapshot.manifest.json").read_text(encoding="utf-8")),
    )
    documents: list[dict[str, Any]] = []
    for artifact in cast("list[dict[str, Any]]", manifest["artifacts"]):
        path = FIXTURE / cast("str", artifact["path"])
        documents.append(cast("dict[str, Any]", json.loads(path.read_text(encoding="utf-8"))))
    return documents


def _concept(
    concept_id: str,
    symbol: str,
    semantic_kind: str,
    *,
    parents: tuple[str, ...] = (),
    profile_extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    profile: dict[str, Any] = {
        "profile_version": "memory-assertion/v1",
        "semantic_kind": semantic_kind,
        "lexicalizations": [],
    }
    if profile_extra:
        profile.update(profile_extra)
    return {
        "id": concept_id,
        "canonical_name": symbol,
        "description": f"{symbol} for validator tests.",
        "sources": ["sources/test/v1/manifest.json#/entities/x"],
        "created_at": "2026-08-09T00:00:00Z",
        "parents": list(parents),
        "supply": {"memory_assertion": profile},
    }


def _operator(
    operator_id: str,
    symbol: str,
    inputs: tuple[str, ...],
    output: str,
    operation: str,
    *,
    profile_extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    profile: dict[str, Any] = {
        "profile_version": "memory-assertion/v1",
        "positional_parameters": [
            {"index": index, "name": f"arg{index}", "definition": f"Argument {index}."}
            for index in range(len(inputs))
        ],
        "proposition_operation": operation,
        "function_semantics": {
            "purity": "pure",
            "deterministic": True,
            "partiality": "total",
        },
        "lexicalizations": [],
    }
    if profile_extra:
        profile.update(profile_extra)
    return {
        "id": operator_id,
        "canonical_name": symbol,
        "description": f"{symbol} for validator tests.",
        "sources": ["sources/test/v1/manifest.json#/entities/x"],
        "created_at": "2026-08-09T00:00:00Z",
        "input_concepts": list(inputs),
        "output_concept": output,
        "supply": {"memory_assertion": profile},
    }


def minimal_snapshot() -> list[dict[str, Any]]:
    """A second, independent snapshot: 5 Concepts, 2 Operators, no violations.

    Small but not degenerate -- it carries an inheritance edge, a disjoint pair, a literal
    Concept with a boolean codec, and one operator of each proposition operation that the
    shipped fixture also uses, so the rules have something to bite on.
    """
    return [
        {
            "ontology": {
                "id": ONTOLOGY_ID,
                "canonical_name": "ValidatorTestOntology",
                "description": "An independent snapshot for validator tests.",
                "sources": ["sources/test/v1/manifest.json#/entities/ontology"],
                "created_at": "2026-08-09T00:00:00Z",
                "version": "1.0.0",
            }
        },
        {
            "concepts": [
                _concept(THING_ID, "Thing", "entity"),
                _concept(
                    PERSON_ID,
                    "Person",
                    "entity",
                    parents=(THING_ID,),
                    profile_extra={"disjoint_with": [ROBOT_ID]},
                ),
                _concept(
                    ROBOT_ID,
                    "Robot",
                    "entity",
                    parents=(THING_ID,),
                    profile_extra={"disjoint_with": [PERSON_ID]},
                ),
                _concept(PROPOSITION_ID, "Proposition", "proposition"),
                _concept(
                    BOOLEAN_ID,
                    "Boolean",
                    "literal_value",
                    profile_extra={
                        "literal_value_contract": {
                            "codec_id": BOOLEAN_CODEC,
                            "canonical_json_kind": "boolean",
                            "equality_mode": "canonical_json_identity",
                            "accepts_null": False,
                        }
                    },
                ),
            ]
        },
        {
            "operators": [
                _operator(
                    KNOWS_ID, "knows", (PERSON_ID, PERSON_ID), BOOLEAN_ID, "none"
                ),
                _operator(
                    BELIEVES_ID,
                    "believes",
                    (PERSON_ID, PROPOSITION_ID),
                    BOOLEAN_ID,
                    "attitude",
                ),
            ]
        },
    ]


def mutate(
    documents: list[dict[str, Any]], edit: Callable[[list[dict[str, Any]]], None]
) -> list[dict[str, Any]]:
    """Deep-copy the shards, then apply `edit` to the copy.

    `edit` receives the copied documents and modifies them in place. Copying first is what
    keeps one test's mutation out of the next test's input.
    """
    copied = copy.deepcopy(documents)
    edit(copied)
    return copied


def concepts_of(documents: list[dict[str, Any]]) -> list[dict[str, Any]]:
    for document in documents:
        if "concepts" in document:
            return cast("list[dict[str, Any]]", document["concepts"])
    raise AssertionError("no concepts shard")


def operators_of(documents: list[dict[str, Any]]) -> list[dict[str, Any]]:
    for document in documents:
        if "operators" in document:
            return cast("list[dict[str, Any]]", document["operators"])
    raise AssertionError("no operators shard")


def profile_of(record: dict[str, Any]) -> dict[str, Any]:
    return cast("dict[str, Any]", cast("dict[str, Any]", record["supply"])["memory_assertion"])


def find_concept(documents: list[dict[str, Any]], concept_id: str) -> dict[str, Any]:
    for record in concepts_of(documents):
        if record["id"] == concept_id:
            return record
    raise AssertionError(f"no concept {concept_id}")


def find_operator(documents: list[dict[str, Any]], operator_id: str) -> dict[str, Any]:
    for record in operators_of(documents):
        if record["id"] == operator_id:
            return record
    raise AssertionError(f"no operator {operator_id}")
