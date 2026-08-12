#!/usr/bin/env python3
"""Validate the memory-assertion/v1 specification package offline.

This is a specification harness, not a runtime NL2KE or semantic validator.
It checks JSON Schema loading, closed examples, evidence hash/offset fixtures,
and the manifest/profile provisioning gates that can be checked locally.
"""

from __future__ import annotations

import copy
import hmac
import hashlib
import json
import math
import re
import shutil
import subprocess
import sys
import unicodedata
import warnings
from pathlib import Path
from typing import Any
from urllib.parse import unquote

warnings.filterwarnings(
    "ignore",
    message="(?:jsonschema.RefResolver is deprecated|Accessing Draft7Validator.resolver is deprecated).*",
    category=DeprecationWarning,
)

from jsonschema import Draft7Validator, FormatChecker, RefResolver  # noqa: E402 - must follow the filterwarnings call above

try:
    from .canonical_text_reference import CanonicalTextError, ReferenceEnvironment
except ImportError:  # Direct execution: python tools/validate_specifications.py
    from canonical_text_reference import CanonicalTextError, ReferenceEnvironment


ROOT = Path(__file__).resolve().parents[1]
SPEC = ROOT / "docs" / "specifications" / "memory-assertion-v1"
SCHEMA_DIR = SPEC / "schema"
FIXTURE = ROOT / "fixtures" / "ontology-snapshot-example"
JCS_HELPER = ROOT / "tools" / "jcs.mjs"
NODE_EXECUTABLE = shutil.which("node")
REFERENCE_MANIFEST = ROOT / "docs" / "references" / "reference-manifest.json"
UPSTREAM_REFERENCE_ROOT = (
    SPEC / "references" / "upstream-ontology-specification-v1"
)
UPSTREAM_REFERENCE_MANIFEST = UPSTREAM_REFERENCE_ROOT / "manifest.json"
CANONICAL_TEXT_VECTORS = SCHEMA_DIR / "canonical-text-reference-vectors.json"
IDENTITY_SEED_REGISTRY = FIXTURE / "build-audit" / "id-seeds.json"
MIGRATION_REQUIRED_FILES = (
    "AGENTS.md",
    "README.md",
    "docs/specifications/memory-assertion-v1/README.md",
    "docs/specifications/memory-assertion-v1/ke-semantic-syntax-standard.md",
    "docs/specifications/memory-assertion-v1/ontology-standard.md",
    "docs/specifications/memory-assertion-v1/ontology-snapshot-packaging.md",
    "docs/specifications/memory-assertion-v1/nl2ke-integration-requirements.md",
    "docs/specifications/memory-assertion-v1/foundation-ontology-v1-build-plan.md",
    "docs/specifications/memory-assertion-v1/schema/memory-assertion-ontology-profile.schema.json",
    "docs/specifications/memory-assertion-v1/schema/memory-assertion-v1.schema.json",
    "docs/specifications/memory-assertion-v1/schema/ontology-snapshot-manifest.schema.json",
    "docs/specifications/memory-assertion-v1/schema/examples.json",
    "docs/specifications/memory-assertion-v1/references/upstream-ontology-specification-v1/ontology.schema.json",
    "docs/specifications/memory-assertion-v1/references/upstream-ontology-specification-v1/ontology.schema.md",
    "docs/specifications/memory-assertion-v1/references/upstream-ontology-specification-v1/manifest.json",
    "docs/references/archive/superseded/external-nl2ke/README.md",
    "docs/references/archive/superseded/external-nl2ke/nl2ke-service-proposal.md",
    "docs/references/project-origin/memory-architecture-report.pdf",
    "docs/references/reference-manifest.json",
    "docs/specifications/memory-assertion-v1/2026-08-08-memory-assertion-v1-contract-migration-design.md",
    "fixtures/ontology-snapshot-example/snapshot.manifest.json",
    "fixtures/ontology-snapshot-example/build-audit/id-seeds.json",
    "tools/validate_specifications.py",
)
MARKDOWN_LINK = re.compile(r"!?\[[^\]]*\]\(([^)]+)\)")
# Tuple form of full JSON Pointer patterns. ``*`` matches one array index.
# Paths outside this allowlist retain their original array order, including
# data stored under any non-memory_assertion supply namespace.
UNORDERED_ARRAY_PATH_PATTERNS = {
    ("artifacts",): "artifacts",
    ("source_manifest",): "source_manifest",
    ("source_manifest", "*", "provenance_refs"): "utf8_string",
    ("required_capabilities",): "utf8_string",
    ("ontology", "sources"): "utf8_string",
    ("concepts",): "concepts",
    ("concepts", "*", "parents"): "utf8_string",
    ("concepts", "*", "sources"): "utf8_string",
    (
        "concepts",
        "*",
        "supply",
        "memory_assertion",
        "disjoint_with",
    ): "utf8_string",
    (
        "concepts",
        "*",
        "supply",
        "memory_assertion",
        "external_mappings",
    ): "external_mappings",
    (
        "concepts",
        "*",
        "supply",
        "memory_assertion",
        "external_mappings",
        "*",
        "provenance_refs",
    ): "utf8_string",
    (
        "concepts",
        "*",
        "supply",
        "memory_assertion",
        "lexicalizations",
    ): "lexicalizations",
    (
        "concepts",
        "*",
        "supply",
        "memory_assertion",
        "lexicalizations",
        "*",
        "source_attestations",
    ): "source_attestations",
    (
        "concepts",
        "*",
        "supply",
        "memory_assertion",
        "lexicalizations",
        "*",
        "source_attestations",
        "*",
        "provenance_refs",
    ): "utf8_string",
    (
        "concepts",
        "*",
        "supply",
        "memory_assertion",
        "literal_value_contract",
        "currency_minor_units",
    ): "currency_minor_units",
    ("operators",): "operators",
    ("operators", "*", "sources"): "utf8_string",
    (
        "operators",
        "*",
        "supply",
        "memory_assertion",
        "external_mappings",
    ): "external_mappings",
    (
        "operators",
        "*",
        "supply",
        "memory_assertion",
        "external_mappings",
        "*",
        "provenance_refs",
    ): "utf8_string",
    (
        "operators",
        "*",
        "supply",
        "memory_assertion",
        "lexicalizations",
    ): "lexicalizations",
    (
        "operators",
        "*",
        "supply",
        "memory_assertion",
        "lexicalizations",
        "*",
        "source_attestations",
    ): "source_attestations",
    (
        "operators",
        "*",
        "supply",
        "memory_assertion",
        "lexicalizations",
        "*",
        "source_attestations",
        "*",
        "provenance_refs",
    ): "utf8_string",
    (
        "operators",
        "*",
        "supply",
        "memory_assertion",
        "definedness_contract",
        "required_input_indexes",
    ): "integer",
}


def reject_duplicate_object_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON object key: {key!r}")
        result[key] = value
    return result


def reject_non_json_constant(token: str) -> None:
    raise ValueError(f"non-JSON numeric constant: {token}")


def read_json(path: Path) -> Any:
    raw = path.read_bytes()
    if raw.startswith(b"\xef\xbb\xbf"):
        raise ValueError(f"UTF-8 BOM is forbidden: {path}")
    text = raw.decode("utf-8", errors="strict")
    return json.loads(
        text,
        object_pairs_hook=reject_duplicate_object_pairs,
        parse_constant=reject_non_json_constant,
    )


def validator_for(path: Path) -> Draft7Validator:
    schema = read_json(path)
    Draft7Validator.check_schema(schema)
    resolver = RefResolver(path.as_uri(), schema)
    return Draft7Validator(schema, resolver=resolver, format_checker=FormatChecker())


def json_pointer_get(document: Any, pointer: str) -> Any:
    current = document
    if pointer in ("", "/"):
        return current
    for token in pointer.lstrip("/").split("/"):
        token = token.replace("~1", "/").replace("~0", "~")
        if isinstance(current, list):
            current = current[int(token)]
        else:
            current = current[token]
    return current


def apply_operation(document: Any, operation: dict[str, Any]) -> None:
    pointer = operation["path"]
    parts = pointer.lstrip("/").split("/") if pointer else []
    parts = [p.replace("~1", "/").replace("~0", "~") for p in parts]
    if not parts:
        raise ValueError("root replacement is not supported in examples")
    parent = document
    for token in parts[:-1]:
        parent = parent[int(token)] if isinstance(parent, list) else parent[token]
    leaf = parts[-1]
    op = operation["op"]
    if op == "add" or op == "replace":
        if isinstance(parent, list):
            if leaf == "-":
                parent.append(copy.deepcopy(operation["value"]))
            else:
                index = int(leaf)
                if op == "add":
                    parent.insert(index, copy.deepcopy(operation["value"]))
                else:
                    parent[index] = copy.deepcopy(operation["value"])
        else:
            parent[leaf] = copy.deepcopy(operation["value"])
    elif op == "remove":
        if isinstance(parent, list):
            del parent[int(leaf)]
        else:
            del parent[leaf]
    else:
        raise ValueError(f"unsupported example operation: {op}")


def materialize_cases(examples: dict[str, Any]) -> dict[str, Any]:
    cases = {case["name"]: case for case in examples.get("cases", [])}
    cache: dict[str, Any] = {}

    def materialize(name: str, stack: tuple[str, ...] = ()) -> Any:
        if name in cache:
            return copy.deepcopy(cache[name])
        if name in stack:
            raise ValueError(f"cyclic example derivation: {' -> '.join(stack + (name,))}")
        case = cases[name]
        if "document" in case:
            document = copy.deepcopy(case["document"])
        else:
            document = materialize(case["derive_from"], stack + (name,))
            for operation in case.get("operations", []):
                apply_operation(document, operation)
        cache[name] = document
        return copy.deepcopy(document)

    return {name: materialize(name) for name in cases}


def _unordered_array_sort_kind(path: tuple[str | int, ...]) -> str | None:
    for pattern, sort_kind in UNORDERED_ARRAY_PATH_PATTERNS.items():
        if len(pattern) == len(path) and all(
            (expected == "*" and isinstance(actual, int))
            or (expected != "*" and expected == actual)
            for expected, actual in zip(pattern, path)
        ):
            return sort_kind
    return None


def canonicalize(value: Any, path: tuple[str | int, ...] = ()) -> Any:
    if isinstance(value, str):
        return unicodedata.normalize("NFC", value)
    if isinstance(value, list):
        items = [
            canonicalize(item, (*path, index))
            for index, item in enumerate(value)
        ]
        sort_kind = _unordered_array_sort_kind(path)
        if sort_kind is not None:
            items.sort(key=lambda item: stable_array_key(sort_kind, item))
        return items
    if isinstance(value, dict):
        normalized: dict[str, Any] = {}
        for key, item in value.items():
            normalized_key = unicodedata.normalize("NFC", key)
            if normalized_key in normalized:
                raise ValueError(f"NFC object key collision: {normalized_key!r}")
            normalized[normalized_key] = canonicalize(
                item, (*path, normalized_key)
            )
        return normalized
    if isinstance(value, int) and not isinstance(value, bool):
        if abs(value) > 9_007_199_254_740_991:
            raise ValueError("JCS integer exceeds the I-JSON safe-integer range")
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("JCS input contains a non-finite number")
    return value


def validate_jcs_domain(value: Any, path: str = "$") -> None:
    if isinstance(value, str):
        if any(0xD800 <= ord(character) <= 0xDFFF for character in value):
            raise ValueError(f"JCS input contains an unpaired Unicode surrogate at {path}")
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            validate_jcs_domain(item, f"{path}[{index}]")
        return
    if isinstance(value, dict):
        for key, item in value.items():
            validate_jcs_domain(key, f"{path} object key")
            validate_jcs_domain(item, f"{path}.{key}")
        return
    if isinstance(value, int) and not isinstance(value, bool):
        if abs(value) > 9_007_199_254_740_991:
            raise ValueError(
                f"JCS integer exceeds the I-JSON safe-integer range at {path}"
            )
        return
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError(f"JCS input contains a non-finite number at {path}")


def stable_array_key(sort_kind: str, item: Any) -> tuple[Any, ...]:
    if sort_kind in {"concepts", "operators"} and isinstance(item, dict):
        primary = (item.get("id", ""), item.get("canonical_name", ""))
    elif sort_kind == "external_mappings" and isinstance(item, dict):
        primary = (
            item.get("source", ""),
            item.get("external_id", ""),
            item.get("relation", ""),
        )
    elif sort_kind == "lexicalizations" and isinstance(item, dict):
        primary = (
            item.get("language", ""),
            item.get("surface_form", ""),
            item.get("surface_relation", ""),
            item.get("disambiguation_status", ""),
        )
    elif sort_kind == "source_attestations" and isinstance(item, dict):
        primary = (
            item.get("source_kind", ""),
            item.get("lemma", ""),
            item.get("sense_id", ""),
            item.get("roleset_id", ""),
        )
    elif sort_kind == "source_manifest" and isinstance(item, dict):
        primary = (
            item.get("source_kind", ""),
            item.get("source_id", ""),
            item.get("version", ""),
            item.get("sha256", ""),
        )
    elif sort_kind == "artifacts" and isinstance(item, dict):
        primary = (item.get("artifact_kind", ""), item.get("path", ""))
    elif sort_kind == "currency_minor_units" and isinstance(item, dict):
        primary = (item.get("currency", ""),)
    elif sort_kind == "utf8_string":
        primary = (0, item.encode("utf-8")) if isinstance(item, str) else (1,)
    elif sort_kind == "integer":
        primary = (
            (0, item)
            if isinstance(item, int) and not isinstance(item, bool)
            else (1,)
        )
    else:
        primary = ()
    return (*primary, canonical_json_bytes(item))


def canonical_json_bytes(value: Any) -> bytes:
    if NODE_EXECUTABLE is None:
        raise RuntimeError("Node.js is required for RFC 8785 JCS validation")
    validate_jcs_domain(value)
    source = json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
    ).encode("utf-8")
    completed = subprocess.run(
        [NODE_EXECUTABLE, str(JCS_HELPER)],
        input=source,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if completed.returncode != 0:
        detail = completed.stderr.decode("utf-8", errors="replace").strip()
        raise ValueError(f"RFC 8785 JCS serialization failed: {detail}")
    return completed.stdout


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(canonicalize(value))).hexdigest()


def exchange_sha256(value: Any) -> str:
    """Hash an exchange object without Snapshot-specific normalization."""

    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def request_hash_preimage(request: dict[str, Any]) -> dict[str, Any]:
    preimage = copy.deepcopy(request)
    preimage["execution"]["credential"].pop("credential_ref")
    return preimage


def request_sha256(request: dict[str, Any]) -> str:
    return exchange_sha256(request_hash_preimage(request))


def record_sha256(value: dict[str, Any], digest_field: str) -> str:
    preimage = copy.deepcopy(value)
    preimage.pop(digest_field, None)
    return exchange_sha256(preimage)


def raw_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _duplicate_values(values: list[Any]) -> list[Any]:
    seen: set[Any] = set()
    duplicates: list[Any] = []
    for value in values:
        if value in seen and value not in duplicates:
            duplicates.append(value)
        seen.add(value)
    return duplicates


def _reference_snapshot_records() -> tuple[
    dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]
]:
    manifest = read_json(FIXTURE / "snapshot.manifest.json")
    concepts: list[dict[str, Any]] = []
    operators: list[dict[str, Any]] = []
    for entry in manifest["artifacts"]:
        document = read_json(FIXTURE / entry["path"])
        if entry["artifact_kind"] == "concepts":
            concepts.extend(document["concepts"])
        elif entry["artifact_kind"] == "operators":
            operators.extend(document["operators"])
    return manifest, concepts, operators


def _request_semantic_errors(
    request: dict[str, Any],
    manifest: dict[str, Any],
    concepts: list[dict[str, Any]],
    operators: list[dict[str, Any]],
) -> list[str]:
    errors: list[str] = []
    try:
        validate_jcs_domain(request)
    except ValueError as exc:
        return [str(exc)]
    messages = request["source"]["messages"]
    message_ids = [message["message_id"] for message in messages]
    revision_ids = [message["message_revision_id"] for message in messages]
    source_orders = [message["source_order"] for message in messages]
    for label, values in (
        ("source message_id", message_ids),
        ("source message_revision_id", revision_ids),
        ("source_order", source_orders),
    ):
        duplicates = _duplicate_values(values)
        if duplicates:
            errors.append(f"duplicate {label}: {duplicates}")
    for message in messages:
        digest = hashlib.sha256(message["content"].encode("utf-8")).hexdigest()
        if digest != message["content_sha256"]:
            errors.append(f"{message['message_id']}: content_sha256 mismatch")
    unknown_focus = set(request["source"]["focus_message_ids"]) - set(message_ids)
    if unknown_focus:
        errors.append(f"focus_message_ids are not closed: {sorted(unknown_focus)}")

    context_items = request["context"]["items"]
    context_ids = [item["context_id"] for item in context_items]
    duplicates = _duplicate_values(context_ids)
    if duplicates:
        errors.append(f"duplicate context_id: {duplicates}")
    for item in context_items:
        digest = hashlib.sha256(item["content"].encode("utf-8")).hexdigest()
        if digest != item["content_sha256"]:
            errors.append(f"{item['context_id']}: content_sha256 mismatch")

    expected_snapshot = {
        "snapshot_id": manifest["snapshot_id"],
        "sha256": manifest["sha256"],
    }
    if request["ontology_snapshot_ref"] != expected_snapshot:
        errors.append("request does not bind the exact conformance Snapshot")

    bundle = request.get(
        "closed_hypothesis_bundle",
        {
            "canonical_bindings": [],
            "canonical_assertions": [],
            "local_declarations": [],
        },
    )
    bindings = bundle["canonical_bindings"]
    assertions = bundle["canonical_assertions"]
    for binding in bindings:
        expected = record_sha256(binding, "binding_sha256")
        if binding["binding_sha256"] != expected:
            errors.append(f"{binding['individual_id']}: binding_sha256 mismatch")
    for assertion in assertions:
        expected = record_sha256(assertion, "assertion_sha256")
        if assertion["assertion_sha256"] != expected:
            errors.append(f"{assertion['assertion_id']}: assertion_sha256 mismatch")
    try:
        environment = ReferenceEnvironment(
            snapshot_ref=expected_snapshot,
            concepts=concepts,
            operators=operators,
            canonical_bindings=bindings,
            local_declarations=bundle["local_declarations"],
            candidate_assertion_ids=[],
            canonical_assertion_ids=[item["assertion_id"] for item in assertions],
            jcs_serializer=lambda value: canonical_json_bytes(value).decode("utf-8"),
        )
        for assertion in assertions:
            environment.render_equation(assertion["ke"], expected_snapshot)
    except CanonicalTextError as exc:
        errors.append(f"ClosedHypothesisBundle is not semantically closed: {exc}")
    return errors


def _processing_scope_errors(
    request: dict[str, Any], response: dict[str, Any]
) -> tuple[list[str], dict[tuple[str, str], dict[str, Any]], list[dict[str, Any]]]:
    errors: list[str] = []
    messages = request["source"]["messages"]
    messages_by_revision = {
        (message["message_id"], message["message_revision_id"]): message
        for message in messages
    }
    messages_by_id = {message["message_id"]: message for message in messages}
    focus = request["source"]["focus_message_ids"]
    scope = response["processing_scope"]
    if scope["received_focus_message_ids"] != focus:
        errors.append("received_focus_message_ids does not echo request focus order")

    source_order = {message["message_id"]: message["source_order"] for message in messages}
    ranges = scope["processed_ranges"]
    expected_order = sorted(
        ranges,
        key=lambda item: (
            source_order.get(item["message_id"], sys.maxsize),
            item["start_char"],
            item["end_char"],
        ),
    )
    if ranges != expected_order:
        errors.append("processed_ranges are not in source/start/end order")

    ranges_by_message: dict[str, list[tuple[int, int]]] = {}
    valid_ranges: list[dict[str, Any]] = []
    for item in ranges:
        message = messages_by_revision.get(
            (item["message_id"], item["message_revision_id"])
        )
        if message is None:
            errors.append(
                "processed_range references an unknown message revision: "
                f"{item['message_id']}/{item['message_revision_id']}"
            )
            continue
        if item["message_id"] not in focus:
            errors.append(
                f"processed_range references non-focus message: {item['message_id']}"
            )
        if item["end_char"] > len(message["content"]):
            errors.append(f"processed_range exceeds message length: {item['message_id']}")
            continue
        ranges_by_message.setdefault(item["message_id"], []).append(
            (item["start_char"], item["end_char"])
        )
        valid_ranges.append(item)

    for message_id, segments in ranges_by_message.items():
        previous_end = -1
        for start, end in segments:
            if start < previous_end:
                errors.append(f"overlapping processed_ranges: {message_id}")
                break
            previous_end = end

    derived_processed_ids = [message_id for message_id in focus if message_id in ranges_by_message]
    if scope["processed_focus_message_ids"] != derived_processed_ids:
        errors.append(
            "processed_focus_message_ids is inconsistent with authoritative processed_ranges"
        )

    if not scope["truncated"]:
        for message_id in focus:
            message = messages_by_id[message_id]
            segments = ranges_by_message.get(message_id, [])
            cursor = 0
            for start, end in segments:
                if start != cursor:
                    errors.append(
                        f"non-truncated processing has a range gap: {message_id} at {cursor}"
                    )
                    break
                cursor = end
            if cursor != len(message["content"]):
                errors.append(
                    f"non-truncated processing does not cover full focus message: {message_id}"
                )
    return errors, messages_by_revision, valid_ranges


def validate_evidence(
    document: dict[str, Any],
    messages: dict[tuple[str, str], dict[str, Any]],
    processed_ranges: list[dict[str, Any]],
) -> list[str]:
    errors: list[str] = []
    evidence_ids = [span["evidence_id"] for span in document.get("source_evidence_spans", [])]
    duplicates = _duplicate_values(evidence_ids)
    if duplicates:
        errors.append(f"duplicate evidence_id: {duplicates}")
    for span in document.get("source_evidence_spans", []):
        digest = hashlib.sha256(span["quote"].encode("utf-8")).hexdigest()
        if digest != span["quote_sha256"]:
            errors.append(f"{span['evidence_id']}: quote_sha256 mismatch")
        if len(span["quote"]) != span["end_char"] - span["start_char"]:
            errors.append(f"{span['evidence_id']}: quote length does not match range")
        message = messages.get((span["message_id"], span["message_revision_id"]))
        if message is None:
            errors.append(
                f"{span['evidence_id']}: Evidence references an unknown message revision"
            )
            continue
        content = message["content"]
        quote = content[span["start_char"] : span["end_char"]]
        if quote != span["quote"]:
            errors.append(f"{span['evidence_id']}: quote does not match offsets")
        within_processed = any(
            item["message_id"] == span["message_id"]
            and item["message_revision_id"] == span["message_revision_id"]
            and item["start_char"] <= span["start_char"]
            and span["end_char"] <= item["end_char"]
            for item in processed_ranges
        )
        if not within_processed:
            errors.append(f"{span['evidence_id']}: Evidence is outside processed_ranges")
    return errors


def subvalidator(root: Draft7Validator, schema: dict[str, Any], definition: str) -> Draft7Validator:
    return Draft7Validator(
        schema["definitions"][definition],
        resolver=root.resolver,
        format_checker=FormatChecker(),
    )


def validate_vector_group(
    vectors: list[dict[str, Any]], validator: Draft7Validator, value_key: str
) -> int:
    for vector in vectors:
        passed = validator.is_valid(vector[value_key])
        expected = bool(vector["expected_valid"])
        if passed != expected:
            raise AssertionError(
                f"vector {vector['name']!r}: expected_valid={expected}, schema_passed={passed}"
            )
    return len(vectors)


def _iter_assertion_refs(term: dict[str, Any]):
    if term.get("kind") == "assertion_ref":
        yield term
    elif term.get("kind") == "operator_application":
        for argument in term.get("arguments", []):
            yield from _iter_assertion_refs(argument)


def _diagnostic_evidence_errors(
    response: dict[str, Any], evidence_ids: set[str]
) -> list[str]:
    errors: list[str] = []

    def visit(value: Any, path: str) -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                child_path = f"{path}/{key}"
                if key == "evidence_id" and item not in evidence_ids:
                    errors.append(f"unclosed diagnostic evidence_id at {child_path}: {item}")
                visit(item, child_path)
        elif isinstance(value, list):
            for index, item in enumerate(value):
                visit(item, f"{path}/{index}")

    for field in (
        "reported_ontology_gaps",
        "reported_capability_gaps",
        "unresolved_items",
        "abstention_reasons",
        "warnings",
    ):
        visit(response[field], field)
    return errors


def _candidate_graph_errors(
    request: dict[str, Any],
    response: dict[str, Any],
    concepts: list[dict[str, Any]],
    operators: list[dict[str, Any]],
) -> list[str]:
    errors: list[str] = []
    hypothesis_ids = [item["hypothesis_id"] for item in response["hypotheses"]]
    ranks = [item["rank"] for item in response["hypotheses"]]
    for label, values in (("hypothesis_id", hypothesis_ids), ("hypothesis rank", ranks)):
        duplicates = _duplicate_values(values)
        if duplicates:
            errors.append(f"duplicate {label}: {duplicates}")

    bundle = request.get(
        "closed_hypothesis_bundle",
        {
            "canonical_bindings": [],
            "canonical_assertions": [],
            "local_declarations": [],
        },
    )
    canonical_ids = [item["assertion_id"] for item in bundle["canonical_assertions"]]
    evidence_ids = {item["evidence_id"] for item in response["source_evidence_spans"]}
    context_ids = {item["context_id"] for item in request["context"]["items"]}
    snapshot_ref = response["ontology_snapshot_ref"]

    for hypothesis in response["hypotheses"]:
        candidates = hypothesis["candidate_assertions"]
        candidate_ids = [item["candidate_id"] for item in candidates]
        duplicates = _duplicate_values(candidate_ids)
        if duplicates:
            errors.append(
                f"{hypothesis['hypothesis_id']}: duplicate candidate_id: {duplicates}"
            )
            continue
        candidate_by_id = {item["candidate_id"]: item for item in candidates}
        roots = hypothesis["root_candidate_ids"]
        unknown_roots = set(roots) - set(candidate_ids)
        if unknown_roots:
            errors.append(
                f"{hypothesis['hypothesis_id']}: unknown root_candidate_ids: "
                f"{sorted(unknown_roots)}"
            )

        try:
            environment = ReferenceEnvironment(
                snapshot_ref=snapshot_ref,
                concepts=concepts,
                operators=operators,
                canonical_bindings=bundle["canonical_bindings"],
                local_declarations=(
                    bundle["local_declarations"] + hypothesis["local_individuals"]
                ),
                candidate_assertion_ids=candidate_ids,
                canonical_assertion_ids=canonical_ids,
                jcs_serializer=lambda value: canonical_json_bytes(value).decode("utf-8"),
            )
            for candidate in candidates:
                environment.render_equation(candidate["ke"], snapshot_ref)
        except CanonicalTextError as exc:
            errors.append(
                f"{hypothesis['hypothesis_id']}: candidate environment is not closed: {exc}"
            )

        graph: dict[str, set[str]] = {candidate_id: set() for candidate_id in candidate_ids}
        for candidate in candidates:
            candidate_id = candidate["candidate_id"]
            terms = [candidate["ke"]["lhs"], candidate["ke"]["rhs"]]
            for term in terms:
                for ref in _iter_assertion_refs(term):
                    if ref["scope"] == "candidate":
                        target = ref["assertion_id"]
                        if target not in candidate_by_id:
                            errors.append(
                                f"{hypothesis['hypothesis_id']}: cross-hypothesis or "
                                f"unknown candidate AssertionRef: {target}"
                            )
                        else:
                            graph[candidate_id].add(target)

            unknown_evidence = set(candidate["source_evidence_ids"]) - evidence_ids
            if unknown_evidence:
                errors.append(
                    f"{hypothesis['hypothesis_id']}/{candidate_id}: unclosed source Evidence: "
                    f"{sorted(unknown_evidence)}"
                )
            unknown_context = set(candidate["context_support_refs"]) - context_ids
            if unknown_context:
                errors.append(
                    f"{hypothesis['hypothesis_id']}/{candidate_id}: unclosed Context refs: "
                    f"{sorted(unknown_context)}"
                )

        for individual in hypothesis["local_individuals"]:
            unknown_evidence = set(individual["mention_evidence_ids"]) - evidence_ids
            if unknown_evidence:
                errors.append(
                    f"{hypothesis['hypothesis_id']}/{individual['individual_id']}: "
                    f"unclosed mention Evidence: {sorted(unknown_evidence)}"
                )

        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(candidate_id: str) -> None:
            if candidate_id in visiting:
                raise ValueError(candidate_id)
            if candidate_id in visited:
                return
            visiting.add(candidate_id)
            for target in graph[candidate_id]:
                visit(target)
            visiting.remove(candidate_id)
            visited.add(candidate_id)

        try:
            for candidate_id in candidate_ids:
                visit(candidate_id)
        except ValueError as exc:
            errors.append(
                f"{hypothesis['hypothesis_id']}: candidate assertion graph cycle at {exc}"
            )

        reachable: set[str] = set()
        pending = [root for root in roots if root in graph]
        while pending:
            candidate_id = pending.pop()
            if candidate_id in reachable:
                continue
            reachable.add(candidate_id)
            pending.extend(graph[candidate_id])
        orphaned = set(candidate_ids) - reachable
        if orphaned:
            errors.append(
                f"{hypothesis['hypothesis_id']}: candidate assertions are not root-reachable: "
                f"{sorted(orphaned)}"
            )
    return errors


def _response_semantic_errors(
    request: dict[str, Any],
    response: dict[str, Any],
    concepts: list[dict[str, Any]],
    operators: list[dict[str, Any]],
) -> list[str]:
    errors: list[str] = []
    if response["request_id"] != request["request_id"]:
        errors.append("response request_id does not match paired request")
    expected_request_hash = request_sha256(request)
    if response["request_hash"] != expected_request_hash:
        errors.append(
            f"request_hash mismatch: expected {expected_request_hash}, "
            f"got {response['request_hash']}"
        )
    if response["ontology_snapshot_ref"] != request["ontology_snapshot_ref"]:
        errors.append("response Snapshot reference does not exactly echo request")

    requested = request["execution"]
    actual = response["execution"]
    for field in ("provider", "model_id", "route_id"):
        if actual[field] != requested["model"][field]:
            errors.append(f"actual execution does not echo requested model.{field}")
    for field in ("strategy_id", "strategy_version"):
        if actual[field] != requested["strategy"][field]:
            errors.append(f"actual execution does not echo requested strategy.{field}")
    expected_fingerprint = requested["credential"]["credential_ref_fingerprint"]
    if actual["credential_ref_fingerprint"] != expected_fingerprint:
        errors.append("credential_ref_fingerprint is not an exact request echo")
    budget = requested["budget"]
    if actual["model_calls"] > budget["max_model_calls"]:
        errors.append("actual model_calls exceeds request budget")
    for actual_field, budget_field in (
        ("input_tokens", "max_input_tokens"),
        ("output_tokens", "max_output_tokens"),
        ("latency_ms", "deadline_ms"),
    ):
        if actual[actual_field] is not None and actual[actual_field] > budget[budget_field]:
            errors.append(f"actual {actual_field} exceeds request budget")

    scope_errors, messages, processed_ranges = _processing_scope_errors(
        request, response
    )
    errors.extend(scope_errors)
    errors.extend(validate_evidence(response, messages, processed_ranges))
    errors.extend(_candidate_graph_errors(request, response, concepts, operators))
    evidence_ids = {item["evidence_id"] for item in response["source_evidence_spans"]}
    errors.extend(_diagnostic_evidence_errors(response, evidence_ids))
    return errors


def _validate_exchange_hash_vectors(examples: dict[str, Any]) -> None:
    vectors = examples["exchange_hash_vectors"]
    credential = vectors["credential_ref_fingerprint"]
    key = bytes.fromhex(credential["test_only_key_hex"])
    observed_credential = hmac.new(
        key,
        credential["credential_ref_utf8"].encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    if observed_credential != credential["expected_hex"]:
        raise AssertionError(
            "credential_ref_fingerprint vector mismatch: "
            f"expected {observed_credential}"
        )
    prompt = vectors["prompt_artifact"]
    observed_prompt = hashlib.sha256(prompt["raw_utf8"].encode("utf-8")).hexdigest()
    if observed_prompt != prompt["expected_hex"]:
        raise AssertionError(
            f"prompt_sha256 vector mismatch: expected {observed_prompt}"
        )


def _error_envelope_semantic_errors(
    request: dict[str, Any] | None, document: dict[str, Any]
) -> list[str]:
    errors: list[str] = []
    diagnostic = document["error"]
    code = diagnostic["code"]
    payload = diagnostic["payload"]
    if document["request_id"] is None:
        if code != "invalid_request":
            errors.append("only invalid_request may omit request_id")
        return errors
    if code == "unsupported_protocol_or_contract":
        return errors
    if request is None:
        errors.append("error envelope has no paired valid request fixture")
        return errors
    if document["request_id"] != request["request_id"]:
        errors.append("error request_id does not match paired request")
    expected_ref = request["ontology_snapshot_ref"]
    if code in {"snapshot_cache_miss", "unsupported_capability", "snapshot_invalid"}:
        if payload["ontology_snapshot_ref"] != expected_ref:
            errors.append(f"{code} does not bind the requested Snapshot")
    elif code == "snapshot_hash_mismatch":
        if (
            payload["snapshot_id"] != expected_ref["snapshot_id"]
            or payload["requested_sha256"] != expected_ref["sha256"]
        ):
            errors.append("snapshot_hash_mismatch does not echo the requested Snapshot")
    return errors


def _build_valid_request_fixture_map(
    examples: dict[str, Any], documents: dict[str, Any]
) -> dict[str, dict[str, Any]]:
    requests: dict[str, dict[str, Any]] = {}
    for case in examples.get("cases", []):
        document = documents[case["name"]]
        if not case["expected_valid"] or document.get("document_kind") != "nl2ke_request":
            continue
        request_id = document["request_id"]
        if request_id in requests:
            raise ValueError(f"duplicate valid request_id fixture: {request_id!r}")
        requests[request_id] = document
    return requests


def validate_exchange() -> tuple[int, int, int, int, int]:
    schema_path = SCHEMA_DIR / "memory-assertion-v1.schema.json"
    schema = read_json(schema_path)
    validator = validator_for(schema_path)
    examples = read_json(SCHEMA_DIR / "examples.json")
    _validate_exchange_hash_vectors(examples)
    valid = 0
    documents = materialize_cases(examples)
    manifest, concepts, operators = _reference_snapshot_records()
    requests = _build_valid_request_fixture_map(examples, documents)
    for case in examples.get("cases", []):
        document = documents[case["name"]]
        schema_errors = list(validator.iter_errors(document))
        semantic_errors: list[str] = []
        document_kind = document.get("document_kind")
        if not schema_errors and document_kind == "nl2ke_request":
            semantic_errors.extend(
                _request_semantic_errors(document, manifest, concepts, operators)
            )
        elif not schema_errors and document_kind == "nl2ke_response":
            request = requests.get(document["request_id"])
            if request is None:
                semantic_errors.append("response has no paired valid request fixture")
            else:
                semantic_errors.extend(
                    _response_semantic_errors(request, document, concepts, operators)
                )
        elif not schema_errors and document_kind == "nl2ke_error":
            request_id = document["request_id"]
            request = requests.get(request_id) if request_id is not None else None
            semantic_errors.extend(
                _error_envelope_semantic_errors(request, document)
            )
        passed = not schema_errors and not semantic_errors
        expected = bool(case["expected_valid"])
        if passed == expected:
            valid += 1
        else:
            detail_parts = [error.message for error in schema_errors[:3]]
            detail_parts.extend(semantic_errors[:3])
            detail = "; ".join(detail_parts)
            raise AssertionError(
                f"example {case['name']!r}: expected_valid={expected}, "
                f"schema_passed={passed}; {detail}"
            )
    leaf_count = validate_vector_group(
        examples.get("leaf_term_examples", []),
        subvalidator(validator, schema, "LeafTerm"),
        "term",
    )
    diagnostic_count = 0
    for vector in examples.get("diagnostic_examples", []):
        target = subvalidator(validator, schema, vector["definition"])
        passed = target.is_valid(vector["diagnostic"])
        expected = bool(vector["expected_valid"])
        if passed != expected:
            raise AssertionError(
                f"diagnostic {vector['name']!r}: expected_valid={expected}, schema_passed={passed}"
            )
        diagnostic_count += 1
    equation_count = validate_vector_group(
        examples.get("canonical_text_examples", []),
        subvalidator(validator, schema, "KnowledgeEquation"),
        "authoritative_json",
    )
    return valid, len(examples.get("cases", [])), leaf_count, diagnostic_count, equation_count


def validate_schemas() -> int:
    schema_names = (
        "memory-assertion-ontology-profile.schema.json",
        "ontology-snapshot-manifest.schema.json",
        "memory-assertion-v1.schema.json",
    )
    for name in schema_names:
        validator_for(SCHEMA_DIR / name)
    return len(schema_names)


def validate_json_inventory() -> int:
    paths = sorted(ROOT.rglob("*.json"))
    for path in paths:
        # Negative conformance vectors intentionally contain values that JCS
        # must reject. Inventory validation therefore checks raw UTF-8, JSON
        # syntax, and exact duplicate keys; vector-specific canonicalization is
        # exercised by validate_jcs_vectors().
        read_json(path)
    return len(paths)


def validate_jcs_vectors() -> tuple[int, int]:
    vectors = read_json(SCHEMA_DIR / "ontology-profile-and-manifest-vectors.json")
    success_count = 0
    for case in vectors.get("jcs_cases", []):
        canonical = canonical_json_bytes(canonicalize(case["value"]))
        expected = case["expected_canonical_text"].encode("utf-8")
        if canonical != expected:
            raise AssertionError(
                f"JCS vector {case['name']!r}: canonical text mismatch"
            )
        digest = hashlib.sha256(canonical).hexdigest()
        if digest != case["expected_sha256"]:
            raise AssertionError(f"JCS vector {case['name']!r}: sha256 mismatch")
        success_count += 1

    error_count = 0
    for case in vectors.get("jcs_error_cases", []):
        try:
            canonical_json_bytes(canonicalize(case["value"]))
        except Exception as exc:
            if case["expected_error"] not in str(exc):
                raise AssertionError(
                    f"JCS error vector {case['name']!r}: "
                    f"expected {case['expected_error']!r}, got {exc!r}"
                ) from exc
        else:
            raise AssertionError(
                f"JCS error vector {case['name']!r}: unexpectedly succeeded"
            )
        error_count += 1
    return success_count, error_count


def _validate_inventory_entries(
    *, manifest_path: Path, base: Path, collection_key: str
) -> tuple[int, dict[str, tuple[int, str]]]:
    manifest = read_json(manifest_path)
    entries = manifest[collection_key]
    observed: dict[str, tuple[int, str]] = {}
    root = ROOT.resolve()
    for entry in entries:
        relative = entry["copied_path"]
        path = (base / relative).resolve()
        if path != root and root not in path.parents:
            raise AssertionError(f"reference path escapes project root: {relative}")
        if not path.is_file():
            raise AssertionError(f"reference file is missing: {relative}")
        size = path.stat().st_size
        digest = raw_sha256(path)
        if size != entry["bytes"]:
            raise AssertionError(
                f"reference byte count mismatch: {relative}; "
                f"manifest={entry['bytes']} actual={size}"
            )
        if digest != entry["sha256"]:
            raise AssertionError(
                f"reference hash mismatch: {relative}; "
                f"manifest={entry['sha256']} actual={digest}"
            )
        observed[str(path).casefold()] = (size, digest)
    return len(entries), observed


def validate_reference_manifests() -> tuple[int, int]:
    reference_count, primary = _validate_inventory_entries(
        manifest_path=REFERENCE_MANIFEST,
        base=ROOT,
        collection_key="files",
    )
    upstream_count, vendored = _validate_inventory_entries(
        manifest_path=UPSTREAM_REFERENCE_MANIFEST,
        base=UPSTREAM_REFERENCE_ROOT,
        collection_key="source_files",
    )
    for path, metadata in vendored.items():
        if path in primary and primary[path] != metadata:
            raise AssertionError(f"reference manifests disagree for {path}")
    return reference_count, upstream_count


def _markdown_target(raw_target: str) -> str:
    target = raw_target.strip()
    if target.startswith("<") and ">" in target:
        return target[1 : target.index(">")]
    # Markdown titles follow whitespace; active local links do not contain
    # unescaped spaces, so splitting here avoids treating a title as a path.
    return target.split(maxsplit=1)[0]


def validate_markdown_links() -> int:
    count = 0
    root = ROOT.resolve()
    for markdown_path in sorted(ROOT.rglob("*.md")):
        text = markdown_path.read_text(encoding="utf-8")
        for match in MARKDOWN_LINK.finditer(text):
            target = _markdown_target(match.group(1))
            if not target or target.startswith("#"):
                continue
            if re.match(r"^[A-Za-z][A-Za-z0-9+.-]*:", target):
                continue
            path_part = unquote(target.split("#", 1)[0])
            resolved = (markdown_path.parent / path_part).resolve()
            if resolved != root and root not in resolved.parents:
                raise AssertionError(
                    f"local Markdown link escapes project root: {markdown_path}: {target}"
                )
            if not resolved.exists():
                raise AssertionError(
                    f"broken local Markdown link: {markdown_path}: {target}"
                )
            count += 1
    return count


def validate_required_migration_files() -> int:
    missing = [relative for relative in MIGRATION_REQUIRED_FILES if not (ROOT / relative).is_file()]
    if missing:
        raise AssertionError(f"migration-required files are missing: {missing}")
    return len(MIGRATION_REQUIRED_FILES)


def validate_profile_vectors(
    profile: Draft7Validator, manifest_validator: Draft7Validator
) -> int:
    vectors = read_json(SCHEMA_DIR / "ontology-profile-and-manifest-vectors.json")
    total = 0
    for group, validator in (
        ("profile_cases", profile),
        ("manifest_cases", manifest_validator),
    ):
        for case in vectors[group]:
            path = (SCHEMA_DIR / case["fixture_path"]).resolve()
            document = read_json(path)
            for operation in case.get("operations", []):
                apply_operation(document, operation)
            passed = validator.is_valid(document)
            expected = bool(case["expected_valid"])
            if passed != expected:
                raise AssertionError(
                    f"profile vector {case['name']!r}: "
                    f"expected_valid={expected}, schema_passed={passed}"
                )
            total += 1
    return total


def _fixture_documents(manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    documents: dict[str, dict[str, Any]] = {}
    fixture_root = FIXTURE.resolve()
    for entry in manifest["artifacts"]:
        path = (FIXTURE / entry["path"]).resolve()
        if fixture_root not in path.parents:
            raise AssertionError(f"artifact escapes fixture root: {entry['path']}")
        documents[entry["path"]] = read_json(path)
    return documents


def _artifact_record_count(kind: str, document: dict[str, Any]) -> int:
    return 1 if kind == "ontology" else len(document[kind])


def _rehash_snapshot(
    manifest: dict[str, Any], documents: dict[str, dict[str, Any]]
) -> None:
    for entry in manifest["artifacts"]:
        document = documents[entry["path"]]
        entry["sha256"] = canonical_sha256(document)
        entry["record_count"] = _artifact_record_count(
            entry["artifact_kind"], document
        )
    root_document = copy.deepcopy(manifest)
    root_document.pop("sha256", None)
    manifest["sha256"] = canonical_sha256(root_document)


def _validate_concept_dag(concepts: dict[str, dict[str, Any]]) -> None:
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(concept_id: str) -> None:
        if concept_id in visiting:
            raise AssertionError(f"Concept inheritance cycle: {concept_id}")
        if concept_id in visited:
            return
        visiting.add(concept_id)
        for parent_id in concepts[concept_id].get("parents", []):
            if parent_id not in concepts:
                raise AssertionError(
                    f"unclosed Concept parent: {concept_id} -> {parent_id}"
                )
            visit(parent_id)
        visiting.remove(concept_id)
        visited.add(concept_id)

    for concept_id in concepts:
        visit(concept_id)


def _concept_ancestor_ids(
    concepts: dict[str, dict[str, Any]], concept_id: str
) -> set[str]:
    ancestors: set[str] = set()
    pending = list(concepts[concept_id].get("parents", []))
    while pending:
        parent_id = pending.pop()
        if parent_id in ancestors:
            continue
        ancestors.add(parent_id)
        pending.extend(concepts[parent_id].get("parents", []))
    return ancestors


def _validate_snapshot_documents(
    manifest: dict[str, Any],
    documents: dict[str, dict[str, Any]],
    *,
    validate_source_files: bool,
) -> int:
    profile = validator_for(
        SCHEMA_DIR / "memory-assertion-ontology-profile.schema.json"
    )
    manifest_validator = validator_for(
        SCHEMA_DIR / "ontology-snapshot-manifest.schema.json"
    )
    manifest_validator.validate(manifest)

    artifact_kinds = [entry["artifact_kind"] for entry in manifest["artifacts"]]
    if artifact_kinds.count("ontology") != 1:
        raise AssertionError("manifest must contain exactly one ontology artifact")
    if "concepts" not in artifact_kinds or "operators" not in artifact_kinds:
        raise AssertionError("manifest must contain Concept and Operator artifacts")
    paths = [entry["path"] for entry in manifest["artifacts"]]
    if len(paths) != len(set(paths)):
        raise AssertionError("manifest artifact paths must be unique")
    if set(paths) != set(documents):
        raise AssertionError("manifest artifacts and loaded documents do not match")
    source_ids = [entry["source_id"] for entry in manifest["source_manifest"]]
    if len(source_ids) != len(set(source_ids)):
        raise AssertionError("manifest source IDs must be unique")

    if manifest["required_capabilities"]:
        raise AssertionError(
            "reference provisioner supports no optional required_capabilities"
        )

    artifacts: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for entry in manifest["artifacts"]:
        document = documents[entry["path"]]
        profile.validate(document)
        digest = canonical_sha256(document)
        if digest != entry["sha256"]:
            raise AssertionError(f"artifact hash mismatch: {entry['path']}")
        count = _artifact_record_count(entry["artifact_kind"], document)
        if count != entry["record_count"]:
            raise AssertionError(f"record_count mismatch: {entry['path']}")
        artifacts.append((entry, document))

    if validate_source_files:
        fixture_root = FIXTURE.resolve()
        declared_source_paths: set[Path] = set()
        for source in manifest["source_manifest"]:
            for provenance_ref in source["provenance_refs"]:
                source_path_text = provenance_ref.split("#", 1)[0]
                path = (FIXTURE / source_path_text).resolve()
                if fixture_root not in path.parents or not path.is_file():
                    raise AssertionError(
                        f"source provenance is not a fixture file: {provenance_ref}"
                    )
                if raw_sha256(path) != source["sha256"]:
                    raise AssertionError(f"source hash mismatch: {source['source_id']}")
                declared_source_paths.add(path)

        def validate_source_ref(reference: str) -> None:
            if re.match(r"^[A-Za-z][A-Za-z0-9+.-]*:", reference):
                raise AssertionError(
                    f"fixture source reference is not locally content-addressed: {reference}"
                )
            path_text, separator, fragment = reference.partition("#")
            path = (FIXTURE / path_text).resolve()
            if path not in declared_source_paths:
                raise AssertionError(
                    f"fixture source reference is absent from source_manifest: {reference}"
                )
            if separator:
                if not fragment.startswith("/"):
                    raise AssertionError(
                        f"fixture source fragment is not a JSON Pointer: {reference}"
                    )
                try:
                    json_pointer_get(read_json(path), fragment)
                except Exception as exc:
                    raise AssertionError(
                        f"fixture source fragment does not resolve: {reference}"
                    ) from exc

        for _, document in artifacts:
            items = []
            if "ontology" in document:
                items.append(document["ontology"])
            items.extend(document.get("concepts", []))
            items.extend(document.get("operators", []))
            for item in items:
                for reference in item.get("sources", []):
                    validate_source_ref(reference)
                extension = item.get("supply", {}).get("memory_assertion", {})
                for lexicalization in extension.get("lexicalizations", []):
                    for attestation in lexicalization["source_attestations"]:
                        for reference in attestation["provenance_refs"]:
                            validate_source_ref(reference)

    root_document = copy.deepcopy(manifest)
    expected_root = root_document.pop("sha256")
    if canonical_sha256(root_document) != expected_root:
        raise AssertionError("snapshot root hash mismatch")

    concepts: dict[str, dict[str, Any]] = {}
    concept_symbols: set[str] = set()
    operators: list[dict[str, Any]] = []
    operator_ids: set[str] = set()
    operator_symbols: set[str] = set()
    ontology_ids: set[str] = set()
    for entry, document in artifacts:
        if entry["artifact_kind"] == "ontology":
            ontology_id = document["ontology"]["id"]
            if ontology_id in ontology_ids:
                raise AssertionError(f"duplicate Ontology ID: {ontology_id}")
            ontology_ids.add(ontology_id)
        elif entry["artifact_kind"] == "concepts":
            for concept in document["concepts"]:
                concept_id = concept["id"]
                symbol = concept["canonical_name"]
                if concept_id in concepts or symbol in concept_symbols:
                    raise AssertionError(
                        f"duplicate Concept ID or Canonical Symbol: {concept_id}/{symbol}"
                    )
                concepts[concept_id] = concept
                concept_symbols.add(symbol)
        else:
            for operator in document["operators"]:
                operator_id = operator["id"]
                symbol = operator["canonical_name"]
                if operator_id in operator_ids or symbol in operator_symbols:
                    raise AssertionError(
                        f"duplicate Operator ID or Canonical Symbol: {operator_id}/{symbol}"
                    )
                operator_ids.add(operator_id)
                operator_symbols.add(symbol)
                operators.append(operator)

    _validate_concept_dag(concepts)
    for concept_id, concept in concepts.items():
        extension = concept["supply"]["memory_assertion"]
        literal_contract = extension.get("literal_value_contract")
        if literal_contract is not None:
            if literal_contract["codec_id"] == "ke-literal:money/v1":
                entries = literal_contract["currency_minor_units"]
                currencies = [entry["currency"] for entry in entries]
                if currencies != sorted(currencies):
                    raise AssertionError(
                        f"currency_minor_units is not currency-sorted: {concept_id}"
                    )
                if len(currencies) != len(set(currencies)):
                    raise AssertionError(
                        f"duplicate currency_minor_units entry: {concept_id}"
                    )
        for disjoint_id in extension.get("disjoint_with", []):
            if disjoint_id not in concepts:
                raise AssertionError(
                    f"unclosed disjoint Concept: {concept_id} -> {disjoint_id}"
                )
            if disjoint_id == concept_id:
                raise AssertionError(f"self-disjoint Concept: {concept_id}")
            reverse = concepts[disjoint_id]["supply"]["memory_assertion"].get(
                "disjoint_with", []
            )
            if concept_id not in reverse:
                raise AssertionError(
                    f"asymmetric disjoint Concept relation: {concept_id}/{disjoint_id}"
                )
            if (
                disjoint_id in _concept_ancestor_ids(concepts, concept_id)
                or concept_id in _concept_ancestor_ids(concepts, disjoint_id)
            ):
                raise AssertionError(
                    f"disjoint Concept ancestor relation: {concept_id}/{disjoint_id}"
                )
        replacement = extension.get("replaced_by")
        if replacement is not None and replacement not in concepts:
            raise AssertionError(f"unclosed Concept replacement: {concept_id}")

    proposition_ids = {
        concept_id
        for concept_id, concept in concepts.items()
        if concept["supply"]["memory_assertion"]["semantic_kind"]
        == "proposition"
    }
    boolean_ids = {
        concept_id
        for concept_id, concept in concepts.items()
        if concept["supply"]["memory_assertion"]
        .get("literal_value_contract", {})
        .get("codec_id")
        == "ke-literal:boolean/v1"
    }
    for operator in operators:
        inputs = operator["input_concepts"]
        if any(
            concept_id not in concepts
            for concept_id in inputs + [operator["output_concept"]]
        ):
            raise AssertionError(f"unclosed operator signature: {operator['id']}")
        extension = operator["supply"]["memory_assertion"]
        parameters = extension["positional_parameters"]
        if [parameter["index"] for parameter in parameters] != list(
            range(len(inputs))
        ):
            raise AssertionError(f"parameter arity/index mismatch: {operator['id']}")
        parameter_names = [parameter["name"] for parameter in parameters]
        if len(parameter_names) != len(set(parameter_names)):
            raise AssertionError(
                f"duplicate positional parameter name: {operator['id']}"
            )
        semantics = extension["function_semantics"]
        if semantics["purity"] != "pure" or "state_parameter_indexes" in semantics:
            raise AssertionError(f"non-pure v1 Operator: {operator['id']}")
        if semantics["partiality"] == "partial":
            raise AssertionError(
                f"partial Operator is quarantined by v1 provisioning: {operator['id']}"
            )
        proposition_count = sum(concept_id in proposition_ids for concept_id in inputs)
        operation = extension["proposition_operation"]
        if operation == "none" and proposition_count:
            raise AssertionError(f"none operator takes Proposition: {operator['id']}")
        if operation == "modifier" and proposition_count != 1:
            raise AssertionError(f"modifier scope mismatch: {operator['id']}")
        if operation == "modifier" and operator["output_concept"] in proposition_ids:
            raise AssertionError(f"modifier outputs Proposition: {operator['id']}")
        if operation == "attitude" and (
            proposition_count != 1 or len(inputs) <= proposition_count
        ):
            raise AssertionError(f"attitude scope mismatch: {operator['id']}")
        if operation == "relation" and proposition_count < 1:
            raise AssertionError(f"relation scope mismatch: {operator['id']}")
        if operation in {"attitude", "relation"} and (
            operator["output_concept"] not in boolean_ids
        ):
            raise AssertionError(f"proposition operation is not Boolean: {operator['id']}")
        replacement = extension.get("replaced_by")
        if replacement is not None and replacement not in operator_ids:
            raise AssertionError(f"unclosed Operator replacement: {operator['id']}")
    return len(artifacts)


def validate_identity_seed_registry(
    documents: dict[str, dict[str, Any]],
) -> int:
    registry = read_json(IDENTITY_SEED_REGISTRY)
    if set(registry) != {"document_kind", "registry_version", "entries"}:
        raise AssertionError("identity seed registry has an open or incomplete shape")
    if registry["document_kind"] != "ontology_identity_seed_registry":
        raise AssertionError("identity seed registry document_kind mismatch")
    if registry["registry_version"] != "ontology-identity-seed-registry/v1":
        raise AssertionError("identity seed registry version mismatch")

    uuid_v4 = re.compile(
        r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
    )
    registry_records: set[tuple[str, str, str]] = set()
    seeds: set[str] = set()
    ids: set[str] = set()
    for entry in registry["entries"]:
        if set(entry) != {"kind", "canonical_name", "identity_seed", "id"}:
            raise AssertionError("identity seed entry has an open or incomplete shape")
        kind = entry["kind"]
        if kind not in {"ontology", "concept", "operator"}:
            raise AssertionError(f"unknown identity seed kind: {kind}")
        seed = entry["identity_seed"]
        if not uuid_v4.fullmatch(seed):
            raise AssertionError(f"identity seed is not lowercase UUIDv4: {seed}")
        digest = hashlib.sha256(f"{kind}:{seed}".encode("utf-8")).hexdigest()
        expected_id = f"{kind}_{digest[:12]}"
        if entry["id"] != expected_id:
            raise AssertionError(
                f"identity seed does not reproduce ID: {entry['id']} != {expected_id}"
            )
        record = (kind, entry["canonical_name"], entry["id"])
        if record in registry_records or seed in seeds or entry["id"] in ids:
            raise AssertionError(f"duplicate identity seed registry entry: {record}")
        registry_records.add(record)
        seeds.add(seed)
        ids.add(entry["id"])

    actual_records: set[tuple[str, str, str]] = set()
    for document in documents.values():
        if "ontology" in document:
            item = document["ontology"]
            actual_records.add(("ontology", item["canonical_name"], item["id"]))
        for collection, kind in (("concepts", "concept"), ("operators", "operator")):
            for item in document.get(collection, []):
                actual_records.add((kind, item["canonical_name"], item["id"]))
    if registry_records != actual_records:
        missing = sorted(actual_records - registry_records)
        extra = sorted(registry_records - actual_records)
        raise AssertionError(
            f"identity seed registry does not exactly cover Snapshot entities: "
            f"missing={missing} extra={extra}"
        )
    return len(registry_records)


def validate_snapshot_fixture() -> tuple[int, int]:
    profile = validator_for(
        SCHEMA_DIR / "memory-assertion-ontology-profile.schema.json"
    )
    manifest_validator = validator_for(
        SCHEMA_DIR / "ontology-snapshot-manifest.schema.json"
    )
    manifest = read_json(FIXTURE / "snapshot.manifest.json")
    documents = _fixture_documents(manifest)
    artifact_count = _validate_snapshot_documents(
        manifest, documents, validate_source_files=True
    )
    validate_identity_seed_registry(documents)
    profile_vector_count = validate_profile_vectors(profile, manifest_validator)
    return artifact_count, profile_vector_count


def validate_snapshot_vectors() -> int:
    vectors = read_json(SCHEMA_DIR / "ontology-profile-and-manifest-vectors.json")
    base_manifest = read_json(FIXTURE / "snapshot.manifest.json")
    base_documents = _fixture_documents(base_manifest)
    count = 0
    for case in vectors.get("snapshot_cases", []):
        manifest = copy.deepcopy(base_manifest)
        documents = copy.deepcopy(base_documents)
        for artifact_change in case.get("artifact_operations", []):
            document = documents[artifact_change["artifact_path"]]
            for operation in artifact_change.get("operations", []):
                apply_operation(document, operation)
        for operation in case.get("manifest_operations", []):
            apply_operation(manifest, operation)
        _rehash_snapshot(manifest, documents)
        try:
            _validate_snapshot_documents(
                manifest, documents, validate_source_files=True
            )
        except Exception:
            passed = False
        else:
            passed = True
        expected = bool(case["expected_valid"])
        if passed != expected:
            raise AssertionError(
                f"snapshot vector {case['name']!r}: "
                f"expected_valid={expected}, provisioning_passed={passed}"
            )
        count += 1
    return count


def _canonical_text_environment() -> tuple[
    ReferenceEnvironment, dict[str, str], dict[str, Any]
]:
    vectors = read_json(CANONICAL_TEXT_VECTORS)
    environment = vectors["environment"]
    manifest_path = (SCHEMA_DIR / environment["snapshot_fixture_path"]).resolve()
    manifest = read_json(manifest_path)
    documents = _fixture_documents(manifest)
    concepts = [
        concept
        for entry in manifest["artifacts"]
        if entry["artifact_kind"] == "concepts"
        for concept in documents[entry["path"]]["concepts"]
    ]
    operators = [
        operator
        for entry in manifest["artifacts"]
        if entry["artifact_kind"] == "operators"
        for operator in documents[entry["path"]]["operators"]
    ]
    snapshot_ref = {
        "snapshot_id": manifest["snapshot_id"],
        "sha256": manifest["sha256"],
    }

    def jcs_text(value: Any) -> str:
        return canonical_json_bytes(canonicalize(value)).decode("utf-8")

    reference = ReferenceEnvironment(
        snapshot_ref=snapshot_ref,
        concepts=concepts,
        operators=operators,
        canonical_bindings=environment["canonical_bindings"],
        local_declarations=environment["local_declarations"],
        candidate_assertion_ids=environment["candidate_assertion_ids"],
        canonical_assertion_ids=environment["canonical_assertion_ids"],
        jcs_serializer=jcs_text,
    )
    return reference, snapshot_ref, vectors


def validate_canonical_text_reference() -> tuple[int, int, int]:
    reference, snapshot_ref, vectors = _canonical_text_environment()
    exchange_schema_path = SCHEMA_DIR / "memory-assertion-v1.schema.json"
    exchange_schema = read_json(exchange_schema_path)
    exchange_validator = validator_for(exchange_schema_path)
    leaf_validator = subvalidator(exchange_validator, exchange_schema, "LeafTerm")
    equation_validator = subvalidator(
        exchange_validator, exchange_schema, "KnowledgeEquation"
    )

    leaf_count = 0
    for case in vectors["leaf_cases"]:
        parsed = reference.parse_leaf(case["canonical_text"], snapshot_ref)
        leaf_validator.validate(parsed)
        if parsed != case["authoritative_json"]:
            raise AssertionError(f"Canonical leaf parse mismatch: {case['name']}")
        rendered = reference.render_leaf(case["authoritative_json"], snapshot_ref)
        if rendered != case["canonical_text"]:
            raise AssertionError(f"Canonical leaf render mismatch: {case['name']}")
        leaf_count += 1

    examples = read_json(SCHEMA_DIR / "examples.json")
    equation_count = 0
    for case in examples["canonical_text_examples"]:
        parsed = reference.parse_equation(case["canonical_text"], snapshot_ref)
        equation_validator.validate(parsed)
        if parsed != case["authoritative_json"]:
            raise AssertionError(f"Canonical equation parse mismatch: {case['name']}")
        rendered = reference.render_equation(
            case["authoritative_json"], snapshot_ref
        )
        if rendered != case["canonical_text"]:
            raise AssertionError(f"Canonical equation render mismatch: {case['name']}")
        equation_count += 1

    error_count = 0
    for group, parser in (
        ("leaf_error_cases", reference.parse_leaf),
        ("equation_error_cases", reference.parse_equation),
    ):
        for case in vectors[group]:
            try:
                parser(case["canonical_text"], snapshot_ref)
            except CanonicalTextError as exc:
                if case["expected_error_contains"] not in str(exc):
                    raise AssertionError(
                        f"Canonical error vector {case['name']!r}: "
                        f"unexpected error {exc!r}"
                    ) from exc
            else:
                raise AssertionError(
                    f"Canonical error vector {case['name']!r}: unexpectedly succeeded"
                )
            error_count += 1
    for case in vectors["snapshot_ref_error_cases"]:
        try:
            reference.parse_equation(
                case["canonical_text"], case["snapshot_ref_override"]
            )
        except CanonicalTextError as exc:
            if case["expected_error_contains"] not in str(exc):
                raise AssertionError(
                    f"Canonical Snapshot vector {case['name']!r}: "
                    f"unexpected error {exc!r}"
                ) from exc
        else:
            raise AssertionError(
                f"Canonical Snapshot vector {case['name']!r}: unexpectedly succeeded"
            )
        error_count += 1
    return leaf_count, equation_count, error_count


def main() -> int:
    try:
        schema_count = validate_schemas()
        json_count = validate_json_inventory()
        example_passed, example_total, leaf_count, diagnostic_count, equation_count = (
            validate_exchange()
        )
        artifact_count, profile_vector_count = validate_snapshot_fixture()
        snapshot_vector_count = validate_snapshot_vectors()
        jcs_count, jcs_error_count = validate_jcs_vectors()
        canonical_leaf_count, canonical_equation_count, canonical_error_count = (
            validate_canonical_text_reference()
        )
        reference_count, upstream_reference_count = validate_reference_manifests()
        markdown_link_count = validate_markdown_links()
        required_file_count = validate_required_migration_files()
        print(
            f"OK schemas={schema_count} json_files={json_count} "
            f"examples={example_passed}/{example_total} "
            f"leaf_terms={leaf_count} diagnostics={diagnostic_count} "
            f"equations={equation_count} profile_vectors={profile_vector_count} "
            f"snapshot_vectors={snapshot_vector_count} "
            f"jcs={jcs_count} jcs_errors={jcs_error_count} "
            f"canonical_leaf={canonical_leaf_count} "
            f"canonical_equations={canonical_equation_count} "
            f"canonical_errors={canonical_error_count} "
            f"fixture_artifacts={artifact_count} "
            f"references={reference_count}+{upstream_reference_count} "
            f"markdown_links={markdown_link_count} "
            f"required_files={required_file_count}"
        )
        return 0
    except Exception as exc:  # pragma: no cover - command-line diagnostic
        print(f"FAIL {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
