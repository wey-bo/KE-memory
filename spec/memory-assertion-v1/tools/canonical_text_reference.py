#!/usr/bin/env python3
"""Minimal Canonical Text parser/renderer for specification conformance tests.

This module is deliberately a reference harness, not a production parser. It
implements only the closed memory-assertion/v1 grammar and the environment
checks needed by the shipped conformance vectors.
"""

from __future__ import annotations

import datetime as dt
import json
import re
import unicodedata
from collections.abc import Callable, Iterable, Mapping, Sequence
from typing import Any


JsonObject = dict[str, Any]
JcsSerializer = Callable[[Any], str]

CONCEPT_SYMBOL = re.compile(r"^[A-Z][A-Za-z0-9]*$")
OPERATOR_SYMBOL = re.compile(r"^[a-z][a-z0-9_]*$")
LOCAL_SYMBOL = re.compile(r"^[a-z][a-z0-9_]*$")
RUNTIME_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,254}$")
DECIMAL = re.compile(r"^-?(?:0|[1-9][0-9]*)(?:\.[0-9]*[1-9])?$")
CURRENCY = re.compile(r"^[A-Z]{3}$")
DATETIME_UTC = re.compile(
    r"^(?P<date>[0-9]{4}-[0-9]{2}-[0-9]{2})T"
    r"(?P<time>[0-9]{2}:[0-9]{2}:[0-9]{2})"
    r"(?:\.(?P<fraction>[0-9]{0,8}[1-9]))?Z$"
)
DURATION_SECONDS = re.compile(
    r"^PT(?:0|[1-9][0-9]*)(?:\.[0-9]*[1-9])?S$"
)


class CanonicalTextError(ValueError):
    """Raised when Canonical Text or its bound environment is not closed."""


def _strict_object(pairs: list[tuple[str, Any]]) -> JsonObject:
    result: JsonObject = {}
    for key, value in pairs:
        if key in result:
            raise CanonicalTextError(f"duplicate JSON object key: {key!r}")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> None:
    raise CanonicalTextError(f"non-finite JSON number is forbidden: {value}")


JSON_DECODER = json.JSONDecoder(
    object_pairs_hook=_strict_object,
    parse_constant=_reject_json_constant,
)


def _require_exact_keys(value: Mapping[str, Any], expected: set[str], label: str) -> None:
    actual = set(value)
    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        raise CanonicalTextError(
            f"{label} fields mismatch: missing={missing}, extra={extra}"
        )


def _validate_runtime_id(value: Any, label: str) -> str:
    if not isinstance(value, str):
        raise CanonicalTextError(f"{label} must be a JSON string")
    if any(ord(character) < 0x20 for character in value):
        raise CanonicalTextError(f"{label} contains a control character")
    if any(unicodedata.category(character) == "Cs" for character in value):
        raise CanonicalTextError(f"{label} contains an unpaired surrogate")
    if RUNTIME_ID.fullmatch(value) is None:
        raise CanonicalTextError(f"{label} is not a valid v1 RuntimeId")
    return value


def _validated_id_set(values: Iterable[str], label: str) -> set[str]:
    result: set[str] = set()
    for value in values:
        validated = _validate_runtime_id(value, label)
        if validated in result:
            raise CanonicalTextError(f"duplicate {label}: {validated}")
        result.add(validated)
    return result


def _is_canonical_decimal(value: Any) -> bool:
    return (
        isinstance(value, str)
        and value != "-0"
        and DECIMAL.fullmatch(value) is not None
    )


class ReferenceEnvironment:
    """Exact Snapshot and hypothesis environment for reference round-trips."""

    def __init__(
        self,
        *,
        snapshot_ref: Mapping[str, str],
        concepts: Sequence[Mapping[str, Any]],
        operators: Sequence[Mapping[str, Any]],
        canonical_bindings: Sequence[Mapping[str, Any]],
        local_declarations: Sequence[Mapping[str, Any]],
        candidate_assertion_ids: Iterable[str],
        canonical_assertion_ids: Iterable[str],
        jcs_serializer: JcsSerializer,
    ) -> None:
        _require_exact_keys(snapshot_ref, {"snapshot_id", "sha256"}, "Snapshot ref")
        self.snapshot_ref = {
            "snapshot_id": _validate_runtime_id(snapshot_ref["snapshot_id"], "snapshot_id"),
            "sha256": snapshot_ref["sha256"],
        }
        if re.fullmatch(r"[a-f0-9]{64}", self.snapshot_ref["sha256"]) is None:
            raise CanonicalTextError("Snapshot sha256 must be 64 lowercase hex characters")
        self._jcs_serializer = jcs_serializer

        self.concepts_by_id: dict[str, Mapping[str, Any]] = {}
        self.concepts_by_symbol: dict[str, Mapping[str, Any]] = {}
        for concept in concepts:
            concept_id = concept["id"]
            symbol = concept["canonical_name"]
            if CONCEPT_SYMBOL.fullmatch(symbol) is None:
                raise CanonicalTextError(f"invalid Concept symbol: {symbol!r}")
            if concept_id in self.concepts_by_id or symbol in self.concepts_by_symbol:
                raise CanonicalTextError(f"duplicate Concept identity or symbol: {symbol!r}")
            self.concepts_by_id[concept_id] = concept
            self.concepts_by_symbol[symbol] = concept

        self.operators_by_id: dict[str, Mapping[str, Any]] = {}
        self.operators_by_symbol: dict[str, Mapping[str, Any]] = {}
        for operator in operators:
            operator_id = operator["id"]
            symbol = operator["canonical_name"]
            if OPERATOR_SYMBOL.fullmatch(symbol) is None:
                raise CanonicalTextError(f"invalid Operator symbol: {symbol!r}")
            if operator_id in self.operators_by_id or symbol in self.operators_by_symbol:
                raise CanonicalTextError(f"duplicate Operator identity or symbol: {symbol!r}")
            self.operators_by_id[operator_id] = operator
            self.operators_by_symbol[symbol] = operator

        self.bindings_by_key: dict[tuple[str, str], Mapping[str, Any]] = {}
        self.bindings_by_symbol: dict[str, tuple[str, Mapping[str, Any]]] = {}
        self._add_bindings("canonical", canonical_bindings)
        self._add_bindings("local", local_declarations)

        self.candidate_assertion_ids = _validated_id_set(
            candidate_assertion_ids, "candidate assertion ID"
        )
        self.canonical_assertion_ids = _validated_id_set(
            canonical_assertion_ids, "canonical assertion ID"
        )

    def _add_bindings(
        self, scope: str, bindings: Sequence[Mapping[str, Any]]
    ) -> None:
        for binding in bindings:
            individual_id = _validate_runtime_id(
                binding.get("individual_id"), f"{scope} individual_id"
            )
            local_symbol = binding.get("local_symbol")
            if not isinstance(local_symbol, str) or LOCAL_SYMBOL.fullmatch(local_symbol) is None:
                raise CanonicalTextError(f"invalid Individual local_symbol: {local_symbol!r}")
            naming_concept_id = binding.get("naming_concept_id")
            concept_ids = binding.get("concept_ids")
            if not isinstance(concept_ids, list) or not concept_ids:
                raise CanonicalTextError("Individual concept_ids must be a non-empty list")
            if naming_concept_id not in concept_ids:
                raise CanonicalTextError("naming_concept_id must be present in concept_ids")
            if any(concept_id not in self.concepts_by_id for concept_id in concept_ids):
                raise CanonicalTextError("Individual binding refers to an unknown Concept")
            naming_concept = self.concepts_by_id[naming_concept_id]
            rendered_symbol = f"{naming_concept['canonical_name']}__{local_symbol}"
            key = (scope, individual_id)
            if key in self.bindings_by_key:
                raise CanonicalTextError(f"duplicate {scope} Individual ID: {individual_id}")
            if rendered_symbol in self.bindings_by_symbol:
                raise CanonicalTextError(
                    f"Individual symbol collision across bindings: {rendered_symbol}"
                )
            self.bindings_by_key[key] = binding
            self.bindings_by_symbol[rendered_symbol] = (scope, binding)

    def _require_snapshot(self, snapshot_ref: Mapping[str, str]) -> None:
        if dict(snapshot_ref) != self.snapshot_ref:
            raise CanonicalTextError("Snapshot reference mismatch")

    def _jcs(self, value: Any) -> str:
        try:
            rendered = self._jcs_serializer(value)
        except Exception as exc:  # pragma: no cover - adapter diagnostic
            raise CanonicalTextError(f"JCS serialization failed: {exc}") from exc
        if not isinstance(rendered, str):
            raise CanonicalTextError("JCS serializer must return text")
        return rendered

    def _parse_json_value(self, text: str, label: str) -> Any:
        candidate = text.strip()
        if not candidate:
            raise CanonicalTextError(f"{label} is missing a JSON value")
        try:
            value, end = JSON_DECODER.raw_decode(candidate)
        except CanonicalTextError:
            raise
        except (json.JSONDecodeError, ValueError) as exc:
            raise CanonicalTextError(f"{label} must contain valid JSON: {exc.msg}") from exc
        if end != len(candidate):
            raise CanonicalTextError(f"{label} contains trailing data")
        return value

    def parse_leaf(
        self, canonical_text: str, snapshot_ref: Mapping[str, str]
    ) -> JsonObject:
        self._require_snapshot(snapshot_ref)
        term = self._parse_leaf_unchecked(canonical_text)
        if self.render_leaf(term, snapshot_ref) != canonical_text:
            raise CanonicalTextError("non-canonical LeafTerm text")
        return term

    def _parse_leaf_unchecked(self, text: str) -> JsonObject:
        token = text.strip()
        for scope in ("candidate", "canonical"):
            prefix = f"Assertion::{scope}::"
            if token.startswith(prefix):
                try:
                    value = self._parse_json_value(
                        token[len(prefix) :], "AssertionRef ID"
                    )
                except CanonicalTextError as exc:
                    raise CanonicalTextError(
                        "AssertionRef ID must be a valid JSON string"
                    ) from exc
                assertion_id = _validate_runtime_id(value, "AssertionRef ID")
                known = (
                    self.candidate_assertion_ids
                    if scope == "candidate"
                    else self.canonical_assertion_ids
                )
                if assertion_id not in known:
                    raise CanonicalTextError(f"unknown {scope} assertion ID: {assertion_id}")
                return {
                    "kind": "assertion_ref",
                    "scope": scope,
                    "assertion_id": assertion_id,
                }

        if token.startswith("Concept::"):
            symbol = token[len("Concept::") :]
            concept = self.concepts_by_symbol.get(symbol)
            if concept is None:
                raise CanonicalTextError(f"unknown Concept symbol: {symbol}")
            return {"kind": "ontology_concept_ref", "concept_id": concept["id"]}

        if token.startswith("Operator::"):
            symbol = token[len("Operator::") :]
            operator = self.operators_by_symbol.get(symbol)
            if operator is None:
                raise CanonicalTextError(f"unknown Operator symbol: {symbol}")
            return {"kind": "ontology_operator_ref", "operator_id": operator["id"]}

        individual_match = re.fullmatch(
            r"([A-Z][A-Za-z0-9]*)__([a-z][a-z0-9_]*)", token
        )
        if individual_match:
            resolved = self.bindings_by_symbol.get(token)
            if resolved is None:
                raise CanonicalTextError(f"unknown Individual symbol: {token}")
            scope, binding = resolved
            return {
                "kind": "individual_ref",
                "scope": scope,
                "individual_id": binding["individual_id"],
            }

        typed_match = re.fullmatch(r"([A-Z][A-Za-z0-9]*)::(.+)", token, re.DOTALL)
        if typed_match:
            symbol, json_text = typed_match.groups()
            concept = self.concepts_by_symbol.get(symbol)
            if concept is None:
                raise CanonicalTextError(f"unknown Concept symbol: {symbol}")
            value = self._parse_json_value(json_text, "TypedValue")
            self._validate_literal(concept, value)
            return {
                "kind": "typed_value",
                "concept_id": concept["id"],
                "canonical_value": value,
            }

        raise CanonicalTextError("invalid LeafTerm syntax")

    def render_leaf(
        self, term: Mapping[str, Any], snapshot_ref: Mapping[str, str]
    ) -> str:
        self._require_snapshot(snapshot_ref)
        if not isinstance(term, Mapping):
            raise CanonicalTextError("LeafTerm JSON must be an object")
        kind = term.get("kind")
        if kind == "individual_ref":
            _require_exact_keys(
                term, {"kind", "scope", "individual_id"}, "IndividualRef"
            )
            scope = term["scope"]
            if scope not in {"local", "canonical"}:
                raise CanonicalTextError(f"invalid IndividualRef scope: {scope!r}")
            individual_id = _validate_runtime_id(term["individual_id"], "individual_id")
            binding = self.bindings_by_key.get((scope, individual_id))
            if binding is None:
                raise CanonicalTextError(f"unknown {scope} Individual ID: {individual_id}")
            naming = self.concepts_by_id[binding["naming_concept_id"]]["canonical_name"]
            return f"{naming}__{binding['local_symbol']}"

        if kind == "typed_value":
            _require_exact_keys(
                term, {"kind", "concept_id", "canonical_value"}, "TypedValue"
            )
            concept = self.concepts_by_id.get(term["concept_id"])
            if concept is None:
                raise CanonicalTextError(f"unknown Concept ID: {term['concept_id']}")
            self._validate_literal(concept, term["canonical_value"])
            return f"{concept['canonical_name']}::{self._jcs(term['canonical_value'])}"

        if kind == "assertion_ref":
            _require_exact_keys(
                term, {"kind", "scope", "assertion_id"}, "AssertionRef"
            )
            scope = term["scope"]
            if scope not in {"candidate", "canonical"}:
                raise CanonicalTextError(f"invalid AssertionRef scope: {scope!r}")
            assertion_id = _validate_runtime_id(term["assertion_id"], "AssertionRef ID")
            known = (
                self.candidate_assertion_ids
                if scope == "candidate"
                else self.canonical_assertion_ids
            )
            if assertion_id not in known:
                raise CanonicalTextError(f"unknown {scope} assertion ID: {assertion_id}")
            return f"Assertion::{scope}::{self._jcs(assertion_id)}"

        if kind == "ontology_concept_ref":
            _require_exact_keys(term, {"kind", "concept_id"}, "OntologyConceptRef")
            concept = self.concepts_by_id.get(term["concept_id"])
            if concept is None:
                raise CanonicalTextError(f"unknown Concept ID: {term['concept_id']}")
            return f"Concept::{concept['canonical_name']}"

        if kind == "ontology_operator_ref":
            _require_exact_keys(term, {"kind", "operator_id"}, "OntologyOperatorRef")
            operator = self.operators_by_id.get(term["operator_id"])
            if operator is None:
                raise CanonicalTextError(f"unknown Operator ID: {term['operator_id']}")
            return f"Operator::{operator['canonical_name']}"

        raise CanonicalTextError(f"unknown LeafTerm kind: {kind!r}")

    def parse_equation(
        self, canonical_text: str, snapshot_ref: Mapping[str, str]
    ) -> JsonObject:
        self._require_snapshot(snapshot_ref)
        match = re.match(r"^([a-z][a-z0-9_]*)\(", canonical_text)
        if match is None:
            raise CanonicalTextError("Canonical Text lhs must be an OperatorApplication")
        operator_symbol = match.group(1)
        operator = self.operators_by_symbol.get(operator_symbol)
        if operator is None:
            raise CanonicalTextError(f"unknown Operator symbol: {operator_symbol}")
        close_index = self._find_application_close(canonical_text, match.end())
        if close_index + 1 >= len(canonical_text) or canonical_text[close_index + 1] != "=":
            raise CanonicalTextError("OperatorApplication must be followed immediately by '='")
        arguments_text = canonical_text[match.end() : close_index]
        rhs_text = canonical_text[close_index + 2 :]
        if not rhs_text:
            raise CanonicalTextError("KnowledgeEquation rhs is missing")
        arguments = [
            self._parse_leaf_unchecked(part)
            for part in self._split_arguments(arguments_text)
        ]
        equation: JsonObject = {
            "lhs": {
                "kind": "operator_application",
                "operator_id": operator["id"],
                "arguments": arguments,
            },
            "rhs": self._parse_leaf_unchecked(rhs_text),
        }
        self._validate_equation(equation)
        if self.render_equation(equation, snapshot_ref) != canonical_text:
            raise CanonicalTextError("non-canonical KnowledgeEquation text")
        return equation

    def render_equation(
        self, equation: Mapping[str, Any], snapshot_ref: Mapping[str, str]
    ) -> str:
        self._require_snapshot(snapshot_ref)
        if not isinstance(equation, Mapping):
            raise CanonicalTextError("KnowledgeEquation JSON must be an object")
        _require_exact_keys(equation, {"lhs", "rhs"}, "KnowledgeEquation")
        self._validate_equation(equation)
        lhs = equation["lhs"]
        operator = self.operators_by_id[lhs["operator_id"]]
        arguments = ",".join(
            self.render_leaf(argument, snapshot_ref) for argument in lhs["arguments"]
        )
        rhs = self.render_leaf(equation["rhs"], snapshot_ref)
        return f"{operator['canonical_name']}({arguments})={rhs}"

    @staticmethod
    def _find_application_close(text: str, start: int) -> int:
        string = False
        escaped = False
        container_depth = 0
        for index in range(start, len(text)):
            character = text[index]
            if string:
                if escaped:
                    escaped = False
                elif character == "\\":
                    escaped = True
                elif character == '"':
                    string = False
                continue
            if character == '"':
                string = True
            elif character in "[{":
                container_depth += 1
            elif character in "]}":
                container_depth -= 1
                if container_depth < 0:
                    raise CanonicalTextError("unbalanced JSON container in OperatorApplication")
            elif character == ")" and container_depth == 0:
                return index
            elif character == "(" and container_depth == 0:
                raise CanonicalTextError("nested OperatorApplication is not a LeafTerm")
        raise CanonicalTextError("unterminated OperatorApplication")

    @staticmethod
    def _split_arguments(text: str) -> list[str]:
        if text == "":
            return []
        parts: list[str] = []
        start = 0
        string = False
        escaped = False
        container_depth = 0
        for index, character in enumerate(text):
            if string:
                if escaped:
                    escaped = False
                elif character == "\\":
                    escaped = True
                elif character == '"':
                    string = False
                continue
            if character == '"':
                string = True
            elif character in "[{":
                container_depth += 1
            elif character in "]}":
                container_depth -= 1
                if container_depth < 0:
                    raise CanonicalTextError("unbalanced JSON container in arguments")
            elif character == "," and container_depth == 0:
                parts.append(text[start:index])
                start = index + 1
        if string or container_depth != 0:
            raise CanonicalTextError("unterminated JSON value in arguments")
        parts.append(text[start:])
        if any(part.strip() == "" for part in parts):
            raise CanonicalTextError("empty OperatorApplication argument")
        return parts

    def _validate_equation(self, equation: Mapping[str, Any]) -> None:
        lhs = equation.get("lhs")
        rhs = equation.get("rhs")
        if not isinstance(lhs, Mapping):
            raise CanonicalTextError("KnowledgeEquation lhs must be an OperatorApplication")
        _require_exact_keys(lhs, {"kind", "operator_id", "arguments"}, "OperatorApplication")
        if lhs["kind"] != "operator_application":
            raise CanonicalTextError("KnowledgeEquation lhs must be an OperatorApplication")
        operator = self.operators_by_id.get(lhs["operator_id"])
        if operator is None:
            raise CanonicalTextError(f"unknown Operator ID: {lhs['operator_id']}")
        arguments = lhs["arguments"]
        if not isinstance(arguments, list):
            raise CanonicalTextError("OperatorApplication arguments must be an array")
        expected_inputs = operator["input_concepts"]
        if len(arguments) != len(expected_inputs):
            raise CanonicalTextError(
                f"Operator arity mismatch: expected {len(expected_inputs)}, got {len(arguments)}"
            )
        for index, (argument, expected_concept_id) in enumerate(
            zip(arguments, expected_inputs)
        ):
            self._validate_term_shape(argument)
            if not self._term_matches_concept(argument, expected_concept_id):
                raise CanonicalTextError(
                    f"Operator input type mismatch at index {index}: expected {expected_concept_id}"
                )
        self._validate_term_shape(rhs)
        if not self._term_matches_concept(rhs, operator["output_concept"]):
            raise CanonicalTextError(
                f"Operator output type mismatch: expected {operator['output_concept']}"
            )

    def _validate_term_shape(self, term: Any) -> None:
        if not isinstance(term, Mapping):
            raise CanonicalTextError("LeafTerm JSON must be an object")
        # Rendering performs the closed-field and environment checks without
        # needing a second JSON Schema implementation in this reference module.
        self.render_leaf(term, self.snapshot_ref)

    def _term_matches_concept(
        self, term: Mapping[str, Any], expected_concept_id: str
    ) -> bool:
        kind = term["kind"]
        if kind == "individual_ref":
            binding = self.bindings_by_key[(term["scope"], term["individual_id"])]
            actual_ids = binding["concept_ids"]
        elif kind == "typed_value":
            actual_ids = [term["concept_id"]]
        elif kind == "assertion_ref":
            actual_ids = [
                concept_id
                for concept_id, concept in self.concepts_by_id.items()
                if concept["supply"]["memory_assertion"]["semantic_kind"]
                == "proposition"
            ]
        elif kind in {"ontology_concept_ref", "ontology_operator_ref"}:
            actual_ids = [
                concept_id
                for concept_id, concept in self.concepts_by_id.items()
                if concept["supply"]["memory_assertion"]["semantic_kind"]
                == "ontology_symbol"
            ]
        else:  # render_leaf already rejects unknown kinds
            return False
        return any(
            self._is_subtype(actual_concept_id, expected_concept_id)
            for actual_concept_id in actual_ids
        )

    def _is_subtype(self, actual_concept_id: str, expected_concept_id: str) -> bool:
        pending = [actual_concept_id]
        visited: set[str] = set()
        while pending:
            current = pending.pop()
            if current == expected_concept_id:
                return True
            if current in visited:
                continue
            visited.add(current)
            concept = self.concepts_by_id.get(current)
            if concept is not None:
                pending.extend(concept.get("parents", []))
        return False

    def _validate_literal(self, concept: Mapping[str, Any], value: Any) -> None:
        extension = concept.get("supply", {}).get("memory_assertion", {})
        contract = extension.get("literal_value_contract")
        if contract is None:
            raise CanonicalTextError(
                f"Concept {concept['id']} has no literal_value_contract"
            )
        if value is None:
            raise CanonicalTextError("TypedValue null is forbidden")
        canonical_kind = contract["canonical_json_kind"]
        kind_matches = {
            "boolean": isinstance(value, bool),
            "string": isinstance(value, str),
            "object": isinstance(value, dict),
        }.get(canonical_kind, False)
        if not kind_matches:
            raise CanonicalTextError(
                f"TypedValue JSON kind does not match {canonical_kind} literal contract"
            )

        codec_id = contract["codec_id"]
        if codec_id == "ke-literal:date/v1" and isinstance(value, str):
            try:
                if dt.date.fromisoformat(value).isoformat() != value:
                    raise ValueError
            except ValueError as exc:
                raise CanonicalTextError("Date TypedValue is not canonical ISO 8601") from exc
        elif codec_id == "ke-literal:decimal/v1" and not _is_canonical_decimal(value):
            raise CanonicalTextError("Decimal TypedValue is not canonical")
        elif codec_id == "ke-literal:datetime/v1":
            match = DATETIME_UTC.fullmatch(value) if isinstance(value, str) else None
            if match is None:
                raise CanonicalTextError(
                    "DateTime TypedValue must be canonical UTC ISO 8601 ending in Z"
                )
            try:
                dt.datetime.strptime(
                    f"{match.group('date')}T{match.group('time')}",
                    "%Y-%m-%dT%H:%M:%S",
                )
            except ValueError as exc:
                raise CanonicalTextError(
                    "DateTime TypedValue is not a valid calendar instant"
                ) from exc
        elif codec_id == "ke-literal:duration/v1" and (
            not isinstance(value, str) or DURATION_SECONDS.fullmatch(value) is None
        ):
            raise CanonicalTextError(
                "Duration TypedValue must be canonical non-negative seconds form"
            )
        elif codec_id == "ke-literal:money/v1":
            if not isinstance(value, dict):
                raise CanonicalTextError("Money TypedValue must be an object")
            if set(value) != {"amount", "currency"}:
                raise CanonicalTextError("Money TypedValue fields are not closed")
            currency = value["currency"]
            amount = value["amount"]
            if not isinstance(currency, str) or CURRENCY.fullmatch(currency) is None:
                raise CanonicalTextError("Money TypedValue is not canonical")
            entries = contract.get("currency_minor_units")
            if not isinstance(entries, list) or not entries:
                raise CanonicalTextError("Money literal contract has no currency table")
            currencies = [entry.get("currency") for entry in entries]
            if currencies != sorted(currencies) or len(currencies) != len(set(currencies)):
                raise CanonicalTextError(
                    "Money currency_minor_units must be unique and currency-sorted"
                )
            minor_units_by_currency = {
                entry["currency"]: entry["minor_units"] for entry in entries
            }
            if currency not in minor_units_by_currency:
                raise CanonicalTextError("Money currency is not supported by this Concept")
            minor_units = minor_units_by_currency[currency]
            fraction = f"\\.[0-9]{{{minor_units}}}" if minor_units else ""
            amount_pattern = re.compile(rf"^-?(?:0|[1-9][0-9]*){fraction}$")
            negative_zero = (
                isinstance(amount, str)
                and amount.startswith("-")
                and set(amount[1:].replace(".", "")) <= {"0"}
            )
            if (
                not isinstance(amount, str)
                or amount_pattern.fullmatch(amount) is None
                or negative_zero
            ):
                raise CanonicalTextError(
                    "Money amount does not match the currency minor-unit contract"
                )
        elif codec_id == "ke-literal:quantity/v1":
            if not isinstance(value, dict):
                raise CanonicalTextError("Quantity TypedValue must be an object")
            if set(value) != {"value", "unit"}:
                raise CanonicalTextError("Quantity TypedValue fields are not closed")
            if (
                not _is_canonical_decimal(value["value"])
                or value["unit"] != contract.get("canonical_unit_symbol")
            ):
                raise CanonicalTextError("Quantity TypedValue is not canonical")
        elif codec_id == "ke-literal:text-nfc/v1" and isinstance(value, str):
            if unicodedata.normalize("NFC", value) != value:
                raise CanonicalTextError("Text TypedValue is not NFC-normalized")
