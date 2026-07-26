from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
import hashlib
import re
from typing import cast

from pydantic import BaseModel, ConfigDict

from ke_memory_demo.core.ids import content_id
from ke_memory_demo.core.json import JsonObject, JsonValue, canonical_json
from ke_memory_demo.domain import (
    AssertionRef,
    ConceptRef,
    Expression,
    IndividualRef,
    KnowledgeEquation,
    OperatorRef,
)

from .models import AdmissionAssessment, MemoryNamespace


class KEOLBundle(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    concepts: tuple[JsonObject, ...] = ()
    individuals: tuple[JsonObject, ...] = ()
    operators: tuple[JsonObject, ...] = ()
    assertions: tuple[JsonObject, ...] = ()
    evidence: tuple[JsonObject, ...] = ()
    workflow_runs: tuple[JsonObject, ...] = ()

    def validate_closed(self) -> None:
        concept_ids = _record_ids(self.concepts)
        individual_ids = _record_ids(self.individuals)
        operator_ids = _record_ids(self.operators)
        assertion_ids = _record_ids(self.assertions)
        evidence_ids = _record_ids(self.evidence)
        workflow_run_ids = _record_ids(self.workflow_runs)

        for individual in self.individuals:
            _require_refs(individual, "concept_ids", concept_ids, "concept")
            _require_refs(individual, "evidence_ids", evidence_ids, "evidence")

        for concept in self.concepts:
            _require_refs(concept, "parent_concept_ids", concept_ids, "concept")
            _require_refs(
                concept,
                "created_from_evidence_ids",
                evidence_ids,
                "evidence",
            )
            _require_optional_ref(concept, "workflow_run_id", workflow_run_ids, "workflow run")

        for operator in self.operators:
            _require_refs(
                operator,
                "created_from_evidence_ids",
                evidence_ids,
                "evidence",
            )
            _require_optional_ref(operator, "workflow_run_id", workflow_run_ids, "workflow run")

        for assertion in self.assertions:
            _validate_term(
                _mapping(assertion, "lhs"),
                concept_ids=concept_ids,
                individual_ids=individual_ids,
                operator_ids=operator_ids,
                assertion_ids=assertion_ids,
            )
            _validate_term(
                _mapping(assertion, "rhs"),
                concept_ids=concept_ids,
                individual_ids=individual_ids,
                operator_ids=operator_ids,
                assertion_ids=assertion_ids,
            )
            _require_refs(assertion, "evidence_ids", evidence_ids, "evidence")
            _require_refs(
                assertion,
                "derived_from_assertion_ids",
                assertion_ids,
                "assertion",
            )
            _require_optional_ref(assertion, "workflow_run_id", workflow_run_ids, "workflow run")


class KEOLBundleCompiler:
    """Compile one admitted Knowledge Equation into a closed KEOL JSON bundle."""

    def compile(
        self,
        *,
        namespace: MemoryNamespace,
        equation: KnowledgeEquation,
        assessment: AdmissionAssessment,
        source_messages: Mapping[str, str],
        recorded_at: datetime,
    ) -> KEOLBundle:
        if recorded_at.tzinfo is None or recorded_at.utcoffset() is None:
            raise ValueError("recorded_at must be timezone-aware")

        namespace_payload = cast(JsonObject, namespace.model_dump(mode="json"))
        created_at = recorded_at.isoformat()
        evidence = self._compile_evidence(
            namespace_payload=namespace_payload,
            equation=equation,
            source_messages=source_messages,
        )
        evidence_ids = [cast(str, item["id"]) for item in evidence]
        workflow_run = self._compile_workflow_run(
            namespace_payload=namespace_payload,
            equation=equation,
            created_at=created_at,
        )
        workflow_run_id = cast(str, workflow_run["id"])

        concepts: dict[str, JsonObject] = {}
        individuals: dict[str, JsonObject] = {}
        operators: dict[str, JsonObject] = {}

        def compile_expression(expression: Expression) -> JsonObject:
            if isinstance(expression, ConceptRef):
                record_id = _term_record_id("concept", namespace_payload, expression.term_id)
                concepts.setdefault(
                    record_id,
                    _concept_record(
                        record_id=record_id,
                        source_term_id=expression.term_id,
                        label=expression.label,
                        evidence_ids=evidence_ids,
                        workflow_run_id=workflow_run_id,
                        namespace_payload=namespace_payload,
                        created_at=created_at,
                    ),
                )
                return {"term_type": "concept", "id": record_id, "arguments": []}

            if isinstance(expression, IndividualRef):
                record_id = _term_record_id("individual", namespace_payload, expression.term_id)
                individuals.setdefault(
                    record_id,
                    _individual_record(
                        record_id=record_id,
                        source_term_id=expression.term_id,
                        label=expression.label,
                        evidence_ids=evidence_ids,
                        namespace_payload=namespace_payload,
                    ),
                )
                return {"term_type": "individual", "id": record_id, "arguments": []}

            if isinstance(expression, OperatorRef):
                record_id = _term_record_id("operator", namespace_payload, expression.term_id)
                operators.setdefault(
                    record_id,
                    _operator_record(
                        record_id=record_id,
                        source_term_id=expression.term_id,
                        label=expression.label,
                        evidence_ids=evidence_ids,
                        workflow_run_id=workflow_run_id,
                        namespace_payload=namespace_payload,
                        created_at=created_at,
                    ),
                )
                return {"term_type": "operator", "id": record_id, "arguments": []}

            if isinstance(expression, AssertionRef):
                raise ValueError(f"dangling assertion term: {expression.assertion_id}")

            operator_term = compile_expression(expression.operator)
            operator_id = cast(str, operator_term["id"])
            arguments = [
                cast(
                    JsonValue,
                    {"role": f"arg{index}", "term": compile_expression(argument)},
                )
                for index, argument in enumerate(expression.arguments)
            ]
            return {
                "term_type": "operator_application",
                "operator_id": operator_id,
                "arguments": arguments,
            }

        lhs = compile_expression(equation.lhs)
        rhs = compile_expression(equation.rhs)
        assertion = self._compile_assertion(
            namespace_payload=namespace_payload,
            equation=equation,
            assessment=assessment,
            lhs=lhs,
            rhs=rhs,
            evidence_ids=evidence_ids,
            workflow_run_id=workflow_run_id,
            created_at=created_at,
        )

        bundle = KEOLBundle(
            concepts=tuple(concepts[key] for key in sorted(concepts)),
            individuals=tuple(individuals[key] for key in sorted(individuals)),
            operators=tuple(operators[key] for key in sorted(operators)),
            assertions=(assertion,),
            evidence=tuple(evidence),
            workflow_runs=(workflow_run,),
        )
        bundle.validate_closed()
        return bundle

    @staticmethod
    def _compile_evidence(
        *,
        namespace_payload: JsonObject,
        equation: KnowledgeEquation,
        source_messages: Mapping[str, str],
    ) -> tuple[JsonObject, ...]:
        records: list[JsonObject] = []
        for span in equation.evidence_refs:
            message = source_messages.get(span.message_id)
            if message is None:
                raise ValueError(f"missing source message: {span.message_id}")
            if span.end_char > len(message):
                raise ValueError(f"evidence span is outside source message: {span.message_id}")
            quote = message[span.start_char : span.end_char]
            quote_hash = hashlib.sha256(quote.encode("utf-8")).hexdigest()
            if quote_hash != span.text_hash:
                raise ValueError(f"span text_hash does not match message {span.message_id}")

            identity: JsonObject = {
                "namespace": namespace_payload,
                "message_id": span.message_id,
                "start_char": span.start_char,
                "end_char": span.end_char,
                "text_hash": span.text_hash,
            }
            record_id = content_id("evidence", identity)
            payload: JsonObject = {
                "id": record_id,
                "slug": _slug(span.message_id, _digest(identity)),
                "evidence_type": "message_span",
                "input_json": canonical_json(identity).decode("utf-8"),
                "source_file": "",
                "source_chunk_id": span.message_id,
                "chunk_index": None,
                "entity_id": "",
                "relation_type": "",
                "schema_path": "",
                "quote": quote,
                "content_hash": quote_hash,
                "metadata": {
                    **namespace_payload,
                    "start_char": span.start_char,
                    "end_char": span.end_char,
                    "full_message_hash": hashlib.sha256(message.encode("utf-8")).hexdigest(),
                },
            }
            records.append({**payload, "hash": _digest(payload)})
        return tuple(sorted(records, key=lambda item: cast(str, item["id"])))

    @staticmethod
    def _compile_workflow_run(
        *,
        namespace_payload: JsonObject,
        equation: KnowledgeEquation,
        created_at: str,
    ) -> JsonObject:
        identity: JsonObject = {
            "namespace": namespace_payload,
            "source_run_id": equation.produced_in_run_id,
        }
        record_id = content_id("workflow-run", identity)
        payload: JsonObject = {
            "id": record_id,
            "slug": _slug(equation.produced_in_run_id, _digest(identity)),
            "workflow_name": "online_memory_ingest",
            "status": "succeeded",
            "started_at": created_at,
            "ended_at": created_at,
            "created_by": "ke-memory-demo",
            "steps": [],
            "model": "",
            "prompt_version": "",
            "pipeline_version": "ke-memory-demo/online-v1",
            "parameters": {},
            "metadata": {
                **namespace_payload,
                "source_run_id": equation.produced_in_run_id,
                "source_stage": equation.produced_in_stage,
            },
        }
        return {**payload, "hash": _digest(payload)}

    @staticmethod
    def _compile_assertion(
        *,
        namespace_payload: JsonObject,
        equation: KnowledgeEquation,
        assessment: AdmissionAssessment,
        lhs: JsonObject,
        rhs: JsonObject,
        evidence_ids: list[str],
        workflow_run_id: str,
        created_at: str,
    ) -> JsonObject:
        identity: JsonObject = {
            "namespace": namespace_payload,
            "source_equation_id": equation.id,
        }
        record_id = content_id("assertion", identity)
        temporal_scope = cast(
            JsonObject,
            equation.temporal.model_dump(mode="json", exclude_none=True),
        )
        payload: JsonObject = {
            "id": record_id,
            "slug": _slug(equation.gloss, _digest(identity)),
            "lhs": lhs,
            "rhs": rhs,
            "confidence": assessment.extraction_confidence,
            "status": equation.lifecycle.value,
            "evidence_ids": _json_strings(evidence_ids),
            "derived_from_assertion_ids": [],
            "workflow_run_id": workflow_run_id,
            "temporal_scope": temporal_scope,
            "created_at": created_at,
            "metadata": {
                **namespace_payload,
                "source_equation_id": equation.id,
                "source_equation_revision": equation.revision,
                "source_status": assessment.source_status.value,
                "admission_status": assessment.status.value,
                "memory_kind": assessment.memory_kind.value,
                "extraction_confidence": assessment.extraction_confidence,
                "epistemic_trust": assessment.epistemic_trust,
                "memory_utility": assessment.memory_utility,
                "admission_reasons": _json_strings(assessment.reasons),
                "modality": equation.modality.value,
                "polarity": equation.polarity.value,
                "speaker": equation.speaker.value,
                "gloss": equation.gloss,
                "source_derived_from": _json_strings(equation.derived_from),
                "source_contradicts": _json_strings(equation.contradicts),
                "source_supersedes": _json_strings(equation.supersedes),
            },
        }
        return {**payload, "hash": _digest(payload)}


def _concept_record(
    *,
    record_id: str,
    source_term_id: str,
    label: str,
    evidence_ids: list[str],
    workflow_run_id: str,
    namespace_payload: JsonObject,
    created_at: str,
) -> JsonObject:
    payload: JsonObject = {
        "id": record_id,
        "slug": _slug(label, _digest({"id": record_id})),
        "name": label,
        "kind": "class",
        "aliases": [],
        "parent_concept_ids": [],
        "individuals": [],
        "same_as": [],
        "created_from_evidence_ids": _json_strings(evidence_ids),
        "workflow_run_id": workflow_run_id,
        "source_kind": "extracted",
        "created_at": created_at,
        "metadata": {**namespace_payload, "source_term_id": source_term_id},
    }
    return {**payload, "hash": _digest(payload)}


def _individual_record(
    *,
    record_id: str,
    source_term_id: str,
    label: str,
    evidence_ids: list[str],
    namespace_payload: JsonObject,
) -> JsonObject:
    payload: JsonObject = {
        "id": record_id,
        "slug": _slug(label, _digest({"id": record_id})),
        "name": label,
        "individual_type": "entity_mention",
        "concept_ids": [],
        "source_entity_id": source_term_id,
        "evidence_ids": _json_strings(evidence_ids),
        "metadata": {**namespace_payload, "source_term_id": source_term_id},
    }
    return {**payload, "hash": _digest(payload)}


def _operator_record(
    *,
    record_id: str,
    source_term_id: str,
    label: str,
    evidence_ids: list[str],
    workflow_run_id: str,
    namespace_payload: JsonObject,
    created_at: str,
) -> JsonObject:
    payload: JsonObject = {
        "id": record_id,
        "slug": _slug(label, _digest({"id": record_id})),
        "name": label,
        "operator_type": "relation",
        "aliases": [],
        "input_schema": [],
        "output_schema": {"role": "output"},
        "parent_operator_id": "",
        "inverse_operator_id": "",
        "created_from_evidence_ids": _json_strings(evidence_ids),
        "workflow_run_id": workflow_run_id,
        "source_kind": "extracted",
        "properties": {},
        "created_at": created_at,
        "metadata": {
            **namespace_payload,
            "source_term_id": source_term_id,
            "schema_status": "unbound",
        },
    }
    return {**payload, "hash": _digest(payload)}


def _term_record_id(kind: str, namespace_payload: JsonObject, source_term_id: str) -> str:
    return content_id(
        f"keol-{kind}",
        {"namespace": namespace_payload, "source_term_id": source_term_id},
    )


def _digest(payload: JsonObject) -> str:
    return hashlib.sha256(canonical_json(payload)).hexdigest()


def _json_strings(values: object) -> list[JsonValue]:
    if not isinstance(values, list | tuple):
        raise TypeError("JSON string sequence must be a list or tuple")
    sequence = cast(list[object] | tuple[object, ...], values)
    if any(not isinstance(value, str) for value in sequence):
        raise TypeError("JSON string sequence contains a non-string value")
    return [cast(JsonValue, value) for value in sequence]


def _slug(label: str, digest: str) -> str:
    normalized = "-".join(re.findall(r"[a-z0-9]+", label.casefold()))
    base = normalized[:64].strip("-") or "record"
    return f"{base}-{digest[:12]}"


def _record_ids(records: tuple[JsonObject, ...]) -> set[str]:
    ids = [cast(str, record["id"]) for record in records]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate KEOL record IDs are not allowed")
    return set(ids)


def _mapping(record: JsonObject, field: str) -> JsonObject:
    value = record.get(field)
    if not isinstance(value, dict):
        raise ValueError(f"KEOL {field} must be an object")
    return cast(JsonObject, value)


def _require_refs(
    record: JsonObject,
    field: str,
    available: set[str],
    label: str,
) -> None:
    value = record.get(field, [])
    if not isinstance(value, list):
        raise ValueError(f"KEOL {field} must be a list")
    refs = cast(list[JsonValue], value)
    for ref in refs:
        if not isinstance(ref, str) or ref not in available:
            raise ValueError(f"dangling {label} reference in {field}: {ref}")


def _require_optional_ref(
    record: JsonObject,
    field: str,
    available: set[str],
    label: str,
) -> None:
    value = record.get(field)
    if value in (None, ""):
        return
    if not isinstance(value, str) or value not in available:
        raise ValueError(f"dangling {label} reference in {field}: {value}")


def _validate_term(
    term: JsonObject,
    *,
    concept_ids: set[str],
    individual_ids: set[str],
    operator_ids: set[str],
    assertion_ids: set[str],
) -> None:
    term_type = term.get("term_type")
    expected_ids = {
        "concept": concept_ids,
        "individual": individual_ids,
        "operator": operator_ids,
        "assertion": assertion_ids,
    }
    if isinstance(term_type, str) and term_type in expected_ids:
        term_id = term.get("id")
        if not isinstance(term_id, str) or term_id not in expected_ids[term_type]:
            raise ValueError(f"dangling {term_type} term: {term_id}")
        return
    if term_type != "operator_application":
        raise ValueError(f"unsupported KEOL term_type: {term_type}")

    operator_id = term.get("operator_id")
    if not isinstance(operator_id, str) or operator_id not in operator_ids:
        raise ValueError(f"dangling operator term: {operator_id}")
    arguments = term.get("arguments", [])
    if not isinstance(arguments, list):
        raise ValueError("KEOL term arguments must be a list")
    for argument in cast(list[JsonValue], arguments):
        if not isinstance(argument, dict):
            raise ValueError("KEOL term argument must be an object")
        argument_mapping = cast(JsonObject, argument)
        _validate_term(
            _mapping(argument_mapping, "term"),
            concept_ids=concept_ids,
            individual_ids=individual_ids,
            operator_ids=operator_ids,
            assertion_ids=assertion_ids,
        )
