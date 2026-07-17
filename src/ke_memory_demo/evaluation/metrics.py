from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from typing import Literal, TypeAlias, TypeVar, cast

from pydantic import BaseModel, ConfigDict

from ke_memory_demo.core.json import JsonObject
from ke_memory_demo.domain import (
    AggregateNode,
    Conversation,
    CoverageEntry,
    Exchange,
    KnowledgeEquation,
    Message,
    MessageSpan,
    OntologyBindingStatus,
)
from ke_memory_demo.infra.telemetry import ModelTrace, UsageRecord

from .models import (
    AggregateMetrics,
    EvaluationRun,
    EvaluationStatus,
    GoldSourceMapping,
    GoldSourceStatus,
    JudgeResult,
    OperationUsageMetrics,
    ProbeQuestion,
    QuestionAnswer,
    QuestionCategory,
    QuestionMetrics,
    TurnKEAuditCase,
)


class MetricsInvariantError(ValueError):
    """Evaluation inputs cannot produce trustworthy KE-only metrics."""


RecordT = TypeVar("RecordT")
AuditKind: TypeAlias = Literal[
    "conversation_first",
    "tool_event",
    "unresolved",
    "lifecycle",
    "cross_session",
]


class QuestionMetricInput(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    question: ProbeQuestion
    gold_mapping: GoldSourceMapping
    answer: QuestionAnswer
    judgement: JudgeResult
    conversations: tuple[Conversation, ...]
    current_knowledge_equations: tuple[KnowledgeEquation, ...]
    aggregates: tuple[AggregateNode, ...]


class ComputedMetrics(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    question_metrics: tuple[QuestionMetrics, ...]
    aggregate_metrics: tuple[AggregateMetrics, ...]


def compute_question_metrics(inputs: QuestionMetricInput) -> QuestionMetrics:
    inputs = QuestionMetricInput.model_validate(inputs)
    question = inputs.question
    answer = inputs.answer
    judgement = inputs.judgement
    mapping = inputs.gold_mapping
    if (
        answer.question_id != question.id
        or judgement.question_id != question.id
        or mapping.question_id != question.id
        or answer.conversation_id != question.conversation_id
    ):
        raise MetricsInvariantError("question metric inputs have inconsistent identities")

    offered_ids = {item.evidence_id for item in answer.evidence}
    citation_valid = len(answer.citations) == len(set(answer.citations)) and set(
        answer.citations
    ).issubset(offered_ids)
    evidence_by_id = {item.evidence_id: item for item in answer.evidence}
    citation_traceable = citation_valid and all(
        _evidence_is_traceable(
            evidence_by_id[citation],
            inputs.conversations,
            inputs.current_knowledge_equations,
            inputs.aggregates,
        )
        for citation in answer.citations
    )

    offered_exchange_ids = {
        exchange_id for evidence in answer.evidence for exchange_id in evidence.source_exchange_ids
    }
    source_recall: float | None = None
    complete_evidence: bool | None = None
    if mapping.status is GoldSourceStatus.MAPPED:
        gold = set(mapping.source_exchange_ids)
        if not gold:
            raise MetricsInvariantError("mapped gold source record has no source Exchanges")
        found = gold.intersection(offered_exchange_ids)
        source_recall = len(found) / len(gold)
        complete_evidence = found == gold

    session_by_exchange = {
        exchange.id: session.id
        for conversation in inputs.conversations
        for session in conversation.sessions
        for exchange in session.exchanges
    }
    source_sessions = {
        session_by_exchange[exchange_id]
        for exchange_id in offered_exchange_ids
        if exchange_id in session_by_exchange
    }
    aggregate_ids = {item.id for item in inputs.aggregates}
    used_aggregate = any(
        record_id in aggregate_ids
        for evidence in answer.evidence
        for record_id in evidence.system_record_ids
    )
    return QuestionMetrics(
        question_id=question.id,
        conversation_id=question.conversation_id,
        category=question.category,
        answer_score=judgement.answer_score,
        satisfied_rubrics=sum(item.satisfied for item in judgement.rubric_items),
        rubric_count=len(judgement.rubric_items),
        factual_error=judgement.factual_error,
        unsupported_claim=judgement.unsupported_claim,
        abstention_correct=judgement.abstention_correct,
        source_recall=source_recall,
        complete_evidence=complete_evidence,
        citation_valid=citation_valid,
        citation_traceable=citation_traceable,
        source_session_count=len(source_sessions),
        used_aggregate=used_aggregate,
        evidence_tokens=sum(item.token_count for item in answer.evidence),
        work_usage=answer.usage,
        judge_usage=judgement.usage,
    )


def compute_metrics(
    *,
    run: EvaluationRun,
    questions: Sequence[ProbeQuestion],
    gold_mappings: Sequence[GoldSourceMapping],
    conversations: Sequence[Conversation],
    current_knowledge_equations: Sequence[KnowledgeEquation],
    aggregates: Sequence[AggregateNode],
) -> ComputedMetrics:
    run = EvaluationRun.model_validate(run)
    question_by_id = _unique_by_id(questions, "question")
    mapping_by_id = _unique_by_id(gold_mappings, "gold source mapping", key="question_id")
    answer_by_id = _unique_by_id(run.answers, "answer", key="question_id")
    judgement_by_id = _unique_by_id(run.judgements, "Judge result", key="question_id")
    expected = run.expected_question_ids
    if tuple(sorted(question_by_id)) != expected:
        raise MetricsInvariantError("metric questions do not match the evaluation manifest")
    if tuple(sorted(mapping_by_id)) != expected:
        raise MetricsInvariantError("gold source mappings do not match the evaluation manifest")

    available_ids = tuple(sorted(set(answer_by_id).intersection(judgement_by_id)))
    question_metrics = tuple(
        compute_question_metrics(
            QuestionMetricInput(
                question=question_by_id[question_id],
                gold_mapping=mapping_by_id[question_id],
                answer=answer_by_id[question_id],
                judgement=judgement_by_id[question_id],
                conversations=tuple(conversations),
                current_knowledge_equations=tuple(current_knowledge_equations),
                aggregates=tuple(aggregates),
            )
        )
        for question_id in available_ids
    )
    if run.status is EvaluationStatus.COMPLETE and available_ids != expected:
        raise MetricsInvariantError("complete run lacks complete per-question metric inputs")

    metrics_by_conversation: dict[str, list[QuestionMetrics]] = defaultdict(list)
    metrics_by_category: dict[QuestionCategory, list[QuestionMetrics]] = defaultdict(list)
    for item in question_metrics:
        metrics_by_conversation[item.conversation_id].append(item)
        metrics_by_category[item.category].append(item)
    questions_by_conversation: dict[str, list[ProbeQuestion]] = defaultdict(list)
    questions_by_category: dict[QuestionCategory, list[ProbeQuestion]] = defaultdict(list)
    for item in questions:
        questions_by_conversation[item.conversation_id].append(item)
        questions_by_category[item.category].append(item)
    completed_ids = frozenset(answer_by_id)
    aggregates_out: list[AggregateMetrics] = [
        _aggregate(
            "overall",
            tuple(questions),
            question_metrics,
            completed_ids=completed_ids,
            mappings=mapping_by_id,
        )
    ]
    for conversation_id in sorted(questions_by_conversation):
        aggregates_out.append(
            _aggregate(
                f"conversation:{conversation_id}",
                tuple(questions_by_conversation[conversation_id]),
                tuple(metrics_by_conversation[conversation_id]),
                completed_ids=completed_ids,
                mappings=mapping_by_id,
            )
        )
    for category in QuestionCategory:
        aggregates_out.append(
            _aggregate(
                f"category:{category.value}",
                tuple(questions_by_category[category]),
                tuple(metrics_by_category[category]),
                completed_ids=completed_ids,
                mappings=mapping_by_id,
            )
        )
    return ComputedMetrics(
        question_metrics=question_metrics,
        aggregate_metrics=tuple(aggregates_out),
    )


def aggregate_operation_usage(
    traces: Iterable[ModelTrace],
    *,
    authoritative_usage: Mapping[str, Sequence[UsageRecord]] | None = None,
) -> tuple[OperationUsageMetrics, ...]:
    overrides = {
        operation: tuple(UsageRecord.model_validate(item) for item in records)
        for operation, records in (authoritative_usage or {}).items()
    }
    usage_by_operation: dict[str, list[UsageRecord]] = defaultdict(list)
    for raw_trace in traces:
        trace = ModelTrace.model_validate(raw_trace)
        if trace.context.operation in overrides:
            continue
        if trace.usage is not None:
            usage_by_operation[trace.context.operation].append(trace.usage)
    for operation, records in overrides.items():
        usage_by_operation[operation].extend(records)
    result: list[OperationUsageMetrics] = []
    for operation in sorted(usage_by_operation):
        records = tuple(usage_by_operation[operation])
        costs = tuple(item.provider_cost for item in records)
        result.append(
            OperationUsageMetrics(
                operation=operation,
                call_count=len(records),
                input_tokens=sum(item.input_tokens for item in records),
                output_tokens=sum(item.output_tokens for item in records),
                latency_seconds=sum(item.latency_seconds for item in records),
                provider_cost=(
                    sum(cast(float, item) for item in costs)
                    if all(item is not None for item in costs)
                    else None
                ),
            )
        )
    return tuple(result)


def select_turn_ke_audits(
    conversations: Sequence[Conversation],
    coverage: Sequence[CoverageEntry],
    knowledge_equations: Sequence[KnowledgeEquation],
    aggregates: Sequence[AggregateNode],
) -> tuple[TurnKEAuditCase, ...]:
    ordered_conversations = tuple(sorted(conversations, key=lambda item: item.id))
    exchange_records = tuple(
        (conversation.id, session.id, exchange)
        for conversation in ordered_conversations
        for session in conversation.sessions
        for exchange in session.exchanges
    )
    exchange_records = tuple(
        sorted(exchange_records, key=lambda item: (item[0], item[2].global_ordinal, item[2].id))
    )
    exchange_by_id = {
        exchange.id: exchange for _conversation, _session, exchange in exchange_records
    }
    message_to_exchange = {
        message.id: exchange.id
        for _conversation, _session, exchange in exchange_records
        for message in (exchange.user, exchange.assistant)
    }
    exchange_context = {
        exchange.id: (conversation_id, session_id)
        for conversation_id, session_id, exchange in exchange_records
    }
    equation_records = tuple(KnowledgeEquation.model_validate(item) for item in knowledge_equations)
    aggregate_records = tuple(AggregateNode.model_validate(item) for item in aggregates)
    cases: list[TurnKEAuditCase] = []

    for conversation in ordered_conversations:
        first = min(
            (exchange for session in conversation.sessions for exchange in session.exchanges),
            key=lambda item: (item.global_ordinal, item.id),
        )
        cases.append(
            _audit_case(
                "conversation_first",
                conversation.id,
                (first.id,),
                exchange_by_id,
                message_to_exchange,
                coverage,
                equation_records,
            )
        )

    tool_record = next((item for item in exchange_records if item[2].events), None)
    if tool_record is not None:
        cases.append(
            _audit_case(
                "tool_event",
                tool_record[0],
                (tool_record[2].id,),
                exchange_by_id,
                message_to_exchange,
                coverage,
                equation_records,
            )
        )

    unresolved = next(
        (
            equation
            for equation in sorted(
                equation_records,
                key=lambda item: _equation_sort_key(item, message_to_exchange, exchange_by_id),
            )
            if any(
                binding.status is not OntologyBindingStatus.RESOLVED
                for binding in equation.ontology_bindings
            )
        ),
        None,
    )
    if unresolved is not None:
        exchange_ids = _equation_exchange_ids(unresolved, message_to_exchange, exchange_by_id)
        cases.append(
            _audit_case(
                "unresolved",
                exchange_context[exchange_ids[0]][0],
                exchange_ids,
                exchange_by_id,
                message_to_exchange,
                coverage,
                (unresolved,),
            )
        )

    lifecycle = _first_lifecycle_pair(equation_records, message_to_exchange, exchange_by_id)
    if lifecycle:
        exchange_ids = _ordered_exchange_ids(
            (
                exchange_id
                for equation in lifecycle
                for exchange_id in _equation_exchange_ids(
                    equation,
                    message_to_exchange,
                    exchange_by_id,
                )
            ),
            exchange_by_id,
        )
        cases.append(
            _audit_case(
                "lifecycle",
                exchange_context[exchange_ids[0]][0],
                exchange_ids,
                exchange_by_id,
                message_to_exchange,
                coverage,
                lifecycle,
            )
        )

    cross = _first_cross_session_aggregate(
        aggregate_records,
        message_to_exchange,
        exchange_context,
        exchange_by_id,
    )
    if cross is not None:
        aggregate, exchange_ids = cross
        aggregate_ids = _aggregate_closure_ids(aggregate, aggregate_records)
        member_ids = {
            member_id
            for aggregate_id in aggregate_ids
            for member_id in next(
                item for item in aggregate_records if item.id == aggregate_id
            ).member_refs
        }
        relevant = tuple(item for item in equation_records if item.id in member_ids)
        cases.append(
            _audit_case(
                "cross_session",
                exchange_context[exchange_ids[0]][0],
                exchange_ids,
                exchange_by_id,
                message_to_exchange,
                coverage,
                relevant,
                aggregate_ids=aggregate_ids,
            )
        )
    return tuple(cases)


def _aggregate(
    scope: str,
    questions: Sequence[ProbeQuestion],
    metrics: Sequence[QuestionMetrics],
    *,
    completed_ids: frozenset[str],
    mappings: Mapping[str, GoldSourceMapping],
) -> AggregateMetrics:
    expected_ids = frozenset(item.id for item in questions)
    count = len(expected_ids)
    if count != len(questions):
        raise MetricsInvariantError(f"aggregate scope contains duplicate questions: {scope}")
    completed_count = len(expected_ids.intersection(completed_ids))
    scored_count = len(metrics)
    mapped_source_count = sum(
        mappings[question_id].status is GoldSourceStatus.MAPPED for question_id in expected_ids
    )
    mapped = tuple(item for item in metrics if item.source_recall is not None)
    source_recall_sum = sum(cast(float, item.source_recall) for item in mapped)
    answer_score_sum = sum(item.answer_score for item in metrics)
    return AggregateMetrics(
        scope=scope,
        question_count=count,
        completed_question_count=completed_count,
        scored_question_count=scored_count,
        answer_score_sum=answer_score_sum,
        answer_score_mean=(answer_score_sum / count if count and scored_count == count else None),
        mapped_source_count=mapped_source_count,
        source_recall_sum=source_recall_sum,
        source_recall_mean=(
            source_recall_sum / mapped_source_count
            if mapped_source_count and len(mapped) == mapped_source_count
            else None
        ),
        complete_evidence_count=sum(item.complete_evidence is True for item in mapped),
        citation_valid_count=sum(item.citation_valid for item in metrics),
        citation_traceable_count=sum(item.citation_traceable for item in metrics),
        factual_error_count=sum(item.factual_error for item in metrics),
        unsupported_claim_count=sum(item.unsupported_claim for item in metrics),
    )


def _evidence_is_traceable(
    evidence: object,
    conversations: Sequence[Conversation],
    equations: Sequence[KnowledgeEquation],
    aggregates: Sequence[AggregateNode],
) -> bool:
    from ke_memory_demo.domain import Evidence

    item = Evidence.model_validate(evidence)
    equation_by_id = {record.id: record for record in equations}
    aggregate_by_id = {record.id: record for record in aggregates}
    if not item.system_record_ids:
        return False
    messages: dict[str, Message] = {}
    exchange_by_message: dict[str, str] = {}
    for conversation in conversations:
        for session in conversation.sessions:
            for exchange in session.exchanges:
                for message in (exchange.user, exchange.assistant):
                    messages[message.id] = message
                    exchange_by_message[message.id] = exchange.id

    closure: list[MessageSpan] = []
    for record_id in item.system_record_ids:
        spans = _record_spans(record_id, equation_by_id, aggregate_by_id, frozenset())
        if not spans:
            return False
        closure.extend(spans)
    closure_message_ids: set[str] = set()
    closure_exchange_ids: set[str] = set()
    for span in closure:
        message = messages.get(span.message_id)
        if message is None:
            return False
        try:
            message.validate_span(span)
        except ValueError:
            return False
        closure_message_ids.add(span.message_id)
        closure_exchange_ids.add(exchange_by_message[span.message_id])
    return set(item.source_message_ids).issubset(closure_message_ids) and set(
        item.source_exchange_ids
    ).issubset(closure_exchange_ids)


def _record_spans(
    record_id: str,
    equations: Mapping[str, KnowledgeEquation],
    aggregates: Mapping[str, AggregateNode],
    seen: frozenset[str],
) -> tuple[MessageSpan, ...]:
    if record_id in seen:
        return ()
    next_seen = seen.union((record_id,))
    equation = equations.get(record_id)
    if equation is not None:
        if equation.evidence_refs:
            return equation.evidence_refs
        return tuple(
            span
            for parent_id in equation.derived_from
            for span in _record_spans(parent_id, equations, aggregates, next_seen)
        )
    aggregate = aggregates.get(record_id)
    if aggregate is not None:
        if aggregate.evidence_closure:
            return aggregate.evidence_closure
        return tuple(
            span
            for parent_id in aggregate.member_refs
            for span in _record_spans(parent_id, equations, aggregates, next_seen)
        )
    return ()


def _unique_by_id(
    records: Sequence[RecordT],
    label: str,
    *,
    key: str = "id",
) -> dict[str, RecordT]:
    result: dict[str, RecordT] = {}
    for record in records:
        identifier = getattr(record, key, None)
        if not isinstance(identifier, str) or not identifier:
            raise MetricsInvariantError(f"{label} has no valid identity")
        if identifier in result:
            raise MetricsInvariantError(f"duplicate {label} identity: {identifier}")
        result[identifier] = record
    return result


def _audit_case(
    audit_kind: AuditKind,
    conversation_id: str,
    exchange_ids: Sequence[str],
    exchange_by_id: Mapping[str, Exchange],
    message_to_exchange: Mapping[str, str],
    coverage: Sequence[CoverageEntry],
    equations: Sequence[KnowledgeEquation],
    *,
    aggregate_ids: tuple[str, ...] = (),
) -> TurnKEAuditCase:
    ordered_ids = _ordered_exchange_ids(exchange_ids, exchange_by_id)
    message_ids = {
        message.id
        for exchange_id in ordered_ids
        for message in (exchange_by_id[exchange_id].user, exchange_by_id[exchange_id].assistant)
    }
    relevant = tuple(
        sorted(
            (
                item
                for item in equations
                if any(
                    message_to_exchange.get(span.message_id) in ordered_ids
                    for span in item.evidence_refs
                )
            ),
            key=lambda item: _equation_sort_key(item, message_to_exchange, exchange_by_id),
        )
    )
    coverage_records = tuple(
        sorted(
            (item for item in coverage if item.message_id in message_ids),
            key=lambda item: (item.message_id, item.start_char, item.end_char, item.status.value),
        )
    )
    raw_records = tuple(
        cast(JsonObject, exchange_by_id[exchange_id].model_dump(mode="json"))
        for exchange_id in ordered_ids
    )
    return TurnKEAuditCase(
        audit_kind=audit_kind,
        conversation_id=conversation_id,
        exchange_ids=ordered_ids,
        raw_records=raw_records,
        coverage=coverage_records,
        knowledge_equations=relevant,
        aggregate_ids=aggregate_ids,
    )


def _equation_exchange_ids(
    equation: KnowledgeEquation,
    message_to_exchange: Mapping[str, str],
    exchange_by_id: Mapping[str, Exchange],
) -> tuple[str, ...]:
    return _ordered_exchange_ids(
        (
            message_to_exchange[span.message_id]
            for span in equation.evidence_refs
            if span.message_id in message_to_exchange
        ),
        exchange_by_id,
    )


def _ordered_exchange_ids(
    exchange_ids: Iterable[str],
    exchange_by_id: Mapping[str, Exchange],
) -> tuple[str, ...]:
    return tuple(
        sorted(
            set(exchange_ids),
            key=lambda item: (exchange_by_id[item].global_ordinal, item),
        )
    )


def _equation_sort_key(
    equation: KnowledgeEquation,
    message_to_exchange: Mapping[str, str],
    exchange_by_id: Mapping[str, Exchange],
) -> tuple[int, str, str]:
    exchange_ids = _equation_exchange_ids(equation, message_to_exchange, exchange_by_id)
    ordinal = exchange_by_id[exchange_ids[0]].global_ordinal if exchange_ids else 2**63 - 1
    return ordinal, equation.id, equation.revision


def _first_lifecycle_pair(
    equations: Sequence[KnowledgeEquation],
    message_to_exchange: Mapping[str, str],
    exchange_by_id: Mapping[str, Exchange],
) -> tuple[KnowledgeEquation, ...]:
    ordered = sorted(
        equations,
        key=lambda item: _equation_sort_key(item, message_to_exchange, exchange_by_id),
    )
    by_id: dict[str, list[KnowledgeEquation]] = defaultdict(list)
    for equation in ordered:
        by_id[equation.id].append(equation)
    for equation in ordered:
        related = (*equation.supersedes, *equation.contradicts)
        for related_id in related:
            candidates = by_id.get(related_id)
            if candidates:
                return tuple(
                    sorted(
                        (candidates[-1], equation),
                        key=lambda item: _equation_sort_key(
                            item,
                            message_to_exchange,
                            exchange_by_id,
                        ),
                    )
                )
    return ()


def _first_cross_session_aggregate(
    aggregates: Sequence[AggregateNode],
    message_to_exchange: Mapping[str, str],
    exchange_context: Mapping[str, tuple[str, str]],
    exchange_by_id: Mapping[str, Exchange],
) -> tuple[AggregateNode, tuple[str, ...]] | None:
    candidates: list[tuple[str, int, str, AggregateNode, tuple[str, ...]]] = []
    for aggregate in aggregates:
        exchange_ids = _ordered_exchange_ids(
            (
                message_to_exchange[span.message_id]
                for span in aggregate.evidence_closure
                if span.message_id in message_to_exchange
            ),
            exchange_by_id,
        )
        contexts = {exchange_context[exchange_id] for exchange_id in exchange_ids}
        conversations = {conversation_id for conversation_id, _session_id in contexts}
        sessions = {session_id for _conversation_id, session_id in contexts}
        if len(conversations) == 1 and len(sessions) > 1:
            candidates.append(
                (next(iter(conversations)), aggregate.depth, aggregate.id, aggregate, exchange_ids)
            )
    if not candidates:
        return None
    _conversation_id, _depth, _aggregate_id, aggregate, exchange_ids = min(candidates)
    return aggregate, exchange_ids


def _aggregate_closure_ids(
    root: AggregateNode,
    aggregates: Sequence[AggregateNode],
) -> tuple[str, ...]:
    by_id = {item.id: item for item in aggregates}
    found: set[str] = set()
    pending = [root.id]
    while pending:
        aggregate_id = pending.pop()
        if aggregate_id in found:
            continue
        found.add(aggregate_id)
        aggregate = by_id[aggregate_id]
        pending.extend(member_id for member_id in aggregate.member_refs if member_id in by_id)
    return tuple(sorted(found, key=lambda item: (by_id[item].depth, item)))
