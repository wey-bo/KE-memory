import pytest
from pydantic import ValidationError

from knowledge_pipeline.models import (
    CandidateRanking,
    ContextCompletion,
    DialoguePassOutput,
    Evidence,
    EvidenceDraft,
    KeywordPassOutput,
    KnowledgeDraft,
    OperationEvidenceDraft,
    ReconciliationOperation,
    TurnPassOutput,
)


def evidence(**overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "turn_index": 0,
        "message": "user",
        "occurrence_index": 0,
        "quote": "I prefer tea.",
    }
    value.update(overrides)
    return value


def persisted_evidence(**overrides: object) -> dict[str, object]:
    value = evidence(
        candidate_id="candidate-1",
        message="user",
        evidence_role="user_reported",
        evidence_id="evidence-1",
        start=0,
        end=14,
    )
    value.update(overrides)
    return value


def knowledge(**overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "knowledge_id": "knowledge-1",
        "candidate_id": "candidate-1",
        "statement": "The user prefers tea.",
        "subject": "user",
        "predicate": "prefers",
        "object": "tea",
        "qualifiers": {"modality": "preferred", "polarity": "positive"},
        "source_status": "user_reported",
        "derivation": "explicit",
        "evidence": [evidence()],
        "inference_basis": None,
        "confidence": 0.9,
    }
    value.update(overrides)
    return value


def test_inferred_knowledge_requires_inference_basis() -> None:
    with pytest.raises(ValidationError, match="inference_basis"):
        KnowledgeDraft.model_validate(knowledge(derivation="inferred"))


def test_explicit_knowledge_rejects_inference_basis() -> None:
    with pytest.raises(ValidationError, match="inference_basis"):
        KnowledgeDraft.model_validate(knowledge(inference_basis="The pronoun refers to the user."))


def test_evidence_rejects_negative_occurrence_index() -> None:
    with pytest.raises(ValidationError, match="occurrence_index"):
        EvidenceDraft.model_validate(evidence(occurrence_index=-1))


def test_evidence_draft_rejects_empty_quote() -> None:
    with pytest.raises(ValidationError, match="quote"):
        EvidenceDraft.model_validate(evidence(quote=""))


@pytest.mark.parametrize(("start", "end"), [(-1, 1), (0, -1)])
def test_evidence_rejects_negative_span_bounds(start: int, end: int) -> None:
    with pytest.raises(ValidationError):
        Evidence.model_validate(
            persisted_evidence(start=start, end=end)
        )


def test_evidence_rejects_end_before_start() -> None:
    with pytest.raises(ValidationError, match="end must be greater"):
        Evidence.model_validate(persisted_evidence(start=4, end=3))


@pytest.mark.parametrize(
    "field",
    [
        "evidence_id", "candidate_id", "turn_index", "message", "quote",
        "occurrence_index", "start", "end", "evidence_role",
    ],
)
def test_persisted_evidence_requires_provenance_fields(field: str) -> None:
    value = persisted_evidence()
    value.pop(field)

    with pytest.raises(ValidationError):
        Evidence.model_validate(value)


def test_persisted_evidence_accepts_exact_approved_schema() -> None:
    value = persisted_evidence()

    assert set(value) == {
        "evidence_id", "candidate_id", "turn_index", "message", "quote",
        "occurrence_index", "start", "end", "evidence_role",
    }
    Evidence.model_validate(value)


def test_context_completion_uses_ambiguity_field() -> None:
    completion = ContextCompletion.model_validate(
        {
            "completion_id": "completion-1",
            "candidate_id": "candidate-1",
            "turn_index": 0,
            "kind": "coreference",
            "original_span": "it",
            "interpretation": "tea",
            "evidence": [evidence()],
            "confidence": 0.8,
            "ambiguity": False,
        }
    )
    assert completion.ambiguity is False


def test_models_reject_extra_fields() -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        EvidenceDraft.model_validate(evidence(unexpected=True))


def test_confidence_is_bounded() -> None:
    with pytest.raises(ValidationError, match="confidence"):
        KnowledgeDraft.model_validate(knowledge(confidence=1.1))


@pytest.mark.parametrize(
    ("keywords", "no_keyword_reason"),
    [
        ([], None),
        (
            [
                {
                    "keyword_id": "keyword-1",
                    "knowledge_id": "knowledge-1",
                    "surface": "tea",
                    "normalized_zh": "茶",
                    "query_lemma": "tea",
                    "keyword_type": "entity",
                    "semantic_role": "object",
                    "source_field": "object",
                    "translation_confidence": 1.0,
                }
            ],
            "No useful keyword",
        ),
    ],
)
def test_keyword_item_requires_keywords_xor_no_keyword_reason(
    keywords: list[dict[str, str]], no_keyword_reason: str | None
) -> None:
    with pytest.raises(ValidationError, match="keywords"):
        KeywordPassOutput.model_validate(
            {
                "candidate_id": "candidate-1",
                "items": [
                    {
                        "knowledge_id": "knowledge-1",
                        "keywords": keywords,
                        "no_keyword_reason": no_keyword_reason,
                    }
                ],
            }
        )


def test_selected_candidate_must_be_null() -> None:
    with pytest.raises(ValidationError, match="selected_candidate"):
        CandidateRanking.model_validate(
            {
                "keyword_id": "keyword-1",
                "ranked_items": [
                    {
                        "id": "vocabulary-1",
                        "mapping": "exact",
                        "score": 0.9,
                        "match_basis": "same label",
                    }
                ],
                "selected_candidate": "vocabulary-1",
            }
        )


@pytest.mark.parametrize("field", ["knowledge_id", "statement", "subject", "predicate"])
def test_knowledge_rejects_whitespace_only_required_strings(field: str) -> None:
    with pytest.raises(ValidationError):
        KnowledgeDraft.model_validate(knowledge(**{field: "   "}))


def test_evidence_rejects_whitespace_only_quote() -> None:
    with pytest.raises(ValidationError):
        EvidenceDraft.model_validate(evidence(quote="\t \n"))


def test_knowledge_object_accepts_none_but_rejects_blank_text() -> None:
    assert KnowledgeDraft.model_validate(knowledge(object=None)).object is None
    with pytest.raises(ValidationError):
        KnowledgeDraft.model_validate(knowledge(object="  "))


def operation(**overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "operation_id": "operation-1",
        "candidate_id": "candidate-1",
        "operation": "confirm",
        "targets": ["knowledge-1"],
        "replacement": None,
        "reason": "The evidence confirms the existing knowledge.",
        "evidence": [evidence(evidence_role="user_reported")],
        "confidence": 0.8,
    }
    value.update(overrides)
    return value


@pytest.mark.parametrize(
    "payload",
    [
        operation(operation="confirm", replacement="knowledge-2"),
        operation(operation="correct", replacement=None),
        operation(operation="conflict", targets=["knowledge-1"]),
        operation(operation="conflict", targets=["knowledge-1", "knowledge-2"], replacement="knowledge-3"),
        operation(operation="add", targets=["knowledge-1"]),
        operation(operation="add", replacement=None),
        operation(targets=["knowledge-1", "knowledge-1"]),
    ],
)
def test_reconciliation_operation_rejects_invalid_operation_shape(payload: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        ReconciliationOperation.model_validate(payload)


@pytest.mark.parametrize(
    "payload",
    [
        operation(operation="confirm"),
        operation(operation="correct", replacement="knowledge-2"),
        operation(operation="supersede", replacement=None),
        operation(operation="supersede", replacement="knowledge-2"),
        operation(operation="conflict", targets=["knowledge-1", "knowledge-2"]),
        operation(operation="add", targets=[], replacement="knowledge-2"),
    ],
)
def test_reconciliation_operation_accepts_valid_operation_shape(payload: dict[str, object]) -> None:
    result = ReconciliationOperation.model_validate(payload)
    assert result.replacement is None or isinstance(result.replacement, str)


def test_operation_evidence_requires_explicit_role() -> None:
    with pytest.raises(ValidationError, match="evidence_role"):
        OperationEvidenceDraft.model_validate(evidence())
    item = OperationEvidenceDraft.model_validate(evidence(evidence_role="tool_observed"))
    assert item.evidence_role == "tool_observed"


def test_turn_output_rejects_duplicate_knowledge_and_context_ids() -> None:
    with pytest.raises(ValidationError):
        TurnPassOutput.model_validate(
            {"candidate_id": "candidate-1", "turn_index": 0, "knowledge": [knowledge(), knowledge()]}
        )
    completion = {
        "completion_id": "completion-1", "candidate_id": "candidate-1", "turn_index": 0,
        "kind": "coreference", "original_span": "it", "interpretation": "tea",
        "evidence": [evidence()], "confidence": 0.8, "ambiguity": False,
    }
    with pytest.raises(ValidationError):
        TurnPassOutput.model_validate(
            {"candidate_id": "candidate-1", "turn_index": 0, "context_completions": [completion, completion]}
        )


def test_dialogue_output_rejects_duplicate_knowledge_and_operation_ids() -> None:
    with pytest.raises(ValidationError):
        DialoguePassOutput.model_validate(
            {"candidate_id": "candidate-1", "new_knowledge": [knowledge(), knowledge()]}
        )
    with pytest.raises(ValidationError):
        DialoguePassOutput.model_validate(
            {"candidate_id": "candidate-1", "operations": [operation(), operation()]}
        )


def keyword_item(knowledge_id: str = "knowledge-1", keyword_id: str = "keyword-1") -> dict[str, object]:
    return {
        "knowledge_id": knowledge_id,
        "keywords": [{
            "keyword_id": keyword_id, "knowledge_id": knowledge_id, "surface": "tea",
            "normalized_zh": "tea", "query_lemma": "tea", "keyword_kind": "lexical",
            "keyword_type": "entity", "semantic_role": "object", "source_field": "object",
            "part_of_speech": "noun", "sense_key": "tea_beverage",
            "sense_hint": "tea as a beverage", "lookup_targets": ["wordnet", "schema_org"],
            "normalized_value": None, "datatype": None, "unit": None,
            "translation_confidence": 1.0,
        }],
        "no_keyword_reason": None,
    }


def test_keyword_output_rejects_duplicate_knowledge_and_keyword_ids() -> None:
    with pytest.raises(ValidationError):
        KeywordPassOutput.model_validate({"candidate_id": "candidate-1", "items": [keyword_item(), keyword_item()]})
    with pytest.raises(ValidationError):
        KeywordPassOutput.model_validate(
            {"candidate_id": "candidate-1", "items": [keyword_item(), keyword_item("knowledge-2")]}
        )


def test_keyword_output_accepts_each_valid_xor_case() -> None:
    KeywordPassOutput.model_validate(
        {"candidate_id": "candidate-1", "items": [{"knowledge_id": "knowledge-1", "keywords": [], "no_keyword_reason": "No entity"}]}
    )
    KeywordPassOutput.model_validate({"candidate_id": "candidate-1", "items": [keyword_item()]})


def test_package_exports_public_nested_models() -> None:
    from knowledge_pipeline import KnowledgeKeywordOutput, OperationEvidenceDraft, RankedCandidate

    assert KnowledgeKeywordOutput.__name__ == "KnowledgeKeywordOutput"
    assert OperationEvidenceDraft.__name__ == "OperationEvidenceDraft"
    assert RankedCandidate.__name__ == "RankedCandidate"
