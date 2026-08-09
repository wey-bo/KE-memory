"""Shared access to the shipped memory-assertion/v1 conformance vectors.

The vectors live in the specification package, which is the authoritative contract. These
tests read them rather than restating them: a hand-written example only proves the models
match the author's reading of the spec, which is the thing most likely to be wrong.

Why a JSON-Patch implementation lives here. 31 of the 42 cases are expressed as
`derive_from` plus `operations`, so they must be materialised before use. The spec
package already has `materialize_cases` for exactly this, but importing it would mean
reaching into `spec/memory-assertion-v1/tools/`, whose modules import themselves as
`tools.*` and are driven by `scripts/ci/check-spec.sh`. `testpaths = ["tests"]` exists to
keep the two package systems from seeing each other, and duplicating three patch
operations costs less than breaking that isolation.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, TypeAlias, cast

JsonValue: TypeAlias = "dict[str, Any] | list[Any] | str | int | float | bool | None"
JsonContainer: TypeAlias = "dict[str, Any] | list[Any]"

REPO_ROOT = Path(__file__).resolve().parents[3]
VECTORS = (
    REPO_ROOT
    / "spec/memory-assertion-v1/docs/specifications/memory-assertion-v1/schema/examples.json"
)

EXPECTED_CASE_COUNT = 42
EXPECTED_LEAF_TERM_COUNT = 11


def load_vectors() -> dict[str, Any]:
    return cast("dict[str, Any]", json.loads(VECTORS.read_text(encoding="utf-8")))


def _resolve(document: JsonValue, pointer: str) -> tuple[JsonContainer, str]:
    """Return the container and final token a JSON Pointer addresses."""
    tokens = [token.replace("~1", "/").replace("~0", "~") for token in pointer.split("/")[1:]]
    container: JsonValue = document
    for token in tokens[:-1]:
        if isinstance(container, list):
            container = container[int(token)]
        elif isinstance(container, dict):
            container = container[token]
        else:
            raise AssertionError(f"pointer {pointer} traverses a scalar at {token!r}")
    if not isinstance(container, dict | list):
        raise AssertionError(f"pointer {pointer} does not address a container")
    return container, tokens[-1]


def apply_operations(document: JsonValue, operations: list[dict[str, Any]]) -> JsonValue:
    """Apply the `add`, `remove` and `replace` operations the vectors use.

    Only those three: asserting on the op name rather than ignoring the unknown ones
    means a vector file that starts using `move` or `copy` fails loudly here instead of
    silently producing a document that was never described.
    """
    result = cast("JsonValue", json.loads(json.dumps(document)))
    for operation in operations:
        op = cast("str", operation["op"])
        container, token = _resolve(result, cast("str", operation["path"]))
        if op == "remove":
            if isinstance(container, list):
                del container[int(token)]
            else:
                del container[token]
        elif op in {"add", "replace"}:
            value = cast("JsonValue", operation["value"])
            if isinstance(container, list):
                if token == "-":
                    container.append(value)
                elif op == "add":
                    container.insert(int(token), value)
                else:
                    container[int(token)] = value
            else:
                container[token] = value
        else:
            raise AssertionError(f"vector uses an unsupported patch operation: {op}")
    return result


def materialized_cases() -> dict[str, dict[str, Any]]:
    """Every case as a full document, keyed by name.

    Derivation chains are resolved by repeated passes rather than recursion, because a
    case may derive from another derived case.
    """
    vectors = load_vectors()
    cases = cast("list[dict[str, Any]]", vectors["cases"])
    resolved: dict[str, dict[str, Any]] = {}
    pending = list(cases)
    while pending:
        progressed = False
        still_pending: list[dict[str, Any]] = []
        for case in pending:
            name = cast("str", case["name"])
            if "document" in case:
                resolved[name] = cast("dict[str, Any]", case["document"])
                progressed = True
            elif case["derive_from"] in resolved:
                patched = apply_operations(
                    resolved[cast("str", case["derive_from"])],
                    cast("list[dict[str, Any]]", case["operations"]),
                )
                assert isinstance(patched, dict), f"{name} patched into a non-document"
                resolved[name] = patched
                progressed = True
            else:
                still_pending.append(case)
        if not progressed:
            unresolved = [case["name"] for case in still_pending]
            raise AssertionError(f"unresolvable derive_from chain: {unresolved}")
        pending = still_pending
    return resolved


def case_expectations() -> dict[str, bool]:
    return {case["name"]: case["expected_valid"] for case in load_vectors()["cases"]}
