from __future__ import annotations

import pytest

from knowledge_pipeline.keywords import attach_canonical_keywords, validate_keyword_output


def _knowledge() -> dict[str, object]:
    return {
        "knowledge_id": "K_demo_001",
        "candidate_id": "DEMO",
        "statement": "用户计划在 2024 年 5 月 15 日前完成遗嘱；如果律师批准该草案。",
        "subject": "用户",
        "predicate": "计划完成",
        "object": "遗嘱",
        "qualifiers": {
            "modality": "planned",
            "polarity": "positive",
            "temporal": ["2024 年 5 月 15 日前"],
            "conditions": ["如果律师批准该草案"],
            "scope": ["draft_id=will-42"],
        },
    }


def _payload() -> dict[str, object]:
    return {
        "candidate_id": "DEMO",
        "keyword_id_prefix": "KW_demo_",
        "active_knowledge": [_knowledge()],
    }


def _keyword(
    index: int,
    *,
    surface: str,
    normalized_zh: str,
    query_lemma: str,
    keyword_kind: str,
    keyword_type: str,
    semantic_role: str,
    source_field: str,
    part_of_speech: str,
    sense_key: str | None,
    sense_hint: str,
    lookup_targets: list[str],
    normalized_value: str | None = None,
    datatype: str | None = None,
    unit: str | None = None,
) -> dict[str, object]:
    return {
        "keyword_id": f"KW_demo_{index:04d}",
        "knowledge_id": "K_demo_001",
        "surface": surface,
        "normalized_zh": normalized_zh,
        "query_lemma": query_lemma,
        "keyword_kind": keyword_kind,
        "keyword_type": keyword_type,
        "semantic_role": semantic_role,
        "source_field": source_field,
        "part_of_speech": part_of_speech,
        "sense_key": sense_key,
        "sense_hint": sense_hint,
        "lookup_targets": lookup_targets,
        "normalized_value": normalized_value,
        "datatype": datatype,
        "unit": unit,
        "translation_confidence": 1.0,
    }


def _valid_keywords() -> list[dict[str, object]]:
    return [
        _keyword(
            1,
            surface="遗嘱",
            normalized_zh="遗嘱",
            query_lemma="will",
            keyword_kind="lexical",
            keyword_type="concept",
            semantic_role="object",
            source_field="object",
            part_of_speech="noun",
            sense_key="legal_testament",
            sense_hint="a legal document stating a person's wishes after death",
            lookup_targets=["wordnet", "schema_org"],
        ),
        _keyword(
            2,
            surface="2024 年 5 月 15 日前",
            normalized_zh="2024年5月15日前",
            query_lemma="deadline",
            keyword_kind="literal",
            keyword_type="time",
            semantic_role="time",
            source_field="qualifiers.temporal",
            part_of_speech="none",
            sense_key=None,
            sense_hint="deadline date",
            lookup_targets=["exact"],
            normalized_value="2024-05-15",
            datatype="date",
        ),
        _keyword(
            3,
            surface="如果律师批准该草案",
            normalized_zh="律师批准草案",
            query_lemma="lawyer approval",
            keyword_kind="qualifier",
            keyword_type="condition",
            semantic_role="condition",
            source_field="qualifiers.conditions",
            part_of_speech="none",
            sense_key=None,
            sense_hint="condition requiring lawyer approval",
            lookup_targets=["exact"],
            normalized_value="lawyer_approval",
            datatype="condition",
        ),
        _keyword(
            4,
            surface="planned",
            normalized_zh="计划",
            query_lemma="planned",
            keyword_kind="qualifier",
            keyword_type="modality",
            semantic_role="modality",
            source_field="qualifiers.modality",
            part_of_speech="none",
            sense_key=None,
            sense_hint="planned knowledge modality",
            lookup_targets=["exact"],
            normalized_value="planned",
            datatype="modality",
        ),
        _keyword(
            5,
            surface="draft_id=will-42",
            normalized_zh="遗嘱草案标识 will-42",
            query_lemma="will draft identifier",
            keyword_kind="identifier",
            keyword_type="entity",
            semantic_role="identifier",
            source_field="qualifiers.scope",
            part_of_speech="none",
            sense_key=None,
            sense_hint="identifier of the will draft",
            lookup_targets=["exact"],
            normalized_value="will-42",
            datatype="identifier",
        ),
    ]


def _raw(keywords: list[dict[str, object]]) -> dict[str, object]:
    return {
        "candidate_id": "DEMO",
        "items": [
            {
                "knowledge_id": "K_demo_001",
                "keywords": keywords,
                "no_keyword_reason": None,
            }
        ],
    }


def test_accepts_atomic_keywords_with_complete_qualifier_coverage() -> None:
    validated = validate_keyword_output(_raw(_valid_keywords()), _payload())

    assert len(validated["items"][0]["keywords"]) == 5


def test_rejects_clause_like_lexical_query_lemma() -> None:
    keywords = _valid_keywords()
    keywords[0]["query_lemma"] = (
        "research does not support fixed auditory visual kinesthetic learning style classification"
    )

    with pytest.raises(ValueError, match="atomic"):
        validate_keyword_output(_raw(keywords), _payload())


def test_rejects_free_form_semantic_role() -> None:
    keywords = _valid_keywords()
    keywords[0]["semantic_role"] = "法律文档完成对象"

    with pytest.raises(ValueError, match="semantic_role"):
        validate_keyword_output(_raw(keywords), _payload())


@pytest.mark.parametrize(
    ("removed_index", "message"),
    [
        (1, "temporal"),
        (2, "condition"),
        (3, "modality"),
        (4, "scope"),
    ],
)
def test_requires_complete_qualifier_coverage(removed_index: int, message: str) -> None:
    keywords = _valid_keywords()
    del keywords[removed_index]
    for index, keyword in enumerate(keywords, start=1):
        keyword["keyword_id"] = f"KW_demo_{index:04d}"

    with pytest.raises(ValueError, match=message):
        validate_keyword_output(_raw(keywords), _payload())


def test_assigns_same_canonical_id_to_repeated_lexical_terms() -> None:
    first = _valid_keywords()[0]
    second = {**first, "keyword_id": "KW_other_0001", "knowledge_id": "K_other_001"}
    candidates = [
        {"candidate_id": "DEMO", "items": [{"knowledge_id": "K_demo_001", "keywords": [first]}]},
        {"candidate_id": "OTHER", "items": [{"knowledge_id": "K_other_001", "keywords": [second]}]},
    ]

    registry = attach_canonical_keywords(candidates)

    first_id = candidates[0]["items"][0]["keywords"][0]["canonical_id"]
    second_id = candidates[1]["items"][0]["keywords"][0]["canonical_id"]
    assert first_id == second_id
    assert len(registry) == 1


def test_rejects_duplicate_normalized_keyword_within_one_knowledge_item() -> None:
    keywords = _valid_keywords()
    duplicate = {**keywords[0], "keyword_id": "KW_demo_0006"}
    keywords.append(duplicate)

    with pytest.raises(ValueError, match="duplicate normalized keyword"):
        validate_keyword_output(_raw(keywords), _payload())


def test_requires_negative_polarity_qualifier() -> None:
    payload = _payload()
    payload["active_knowledge"][0]["qualifiers"]["polarity"] = "negative"

    with pytest.raises(ValueError, match="polarity"):
        validate_keyword_output(_raw(_valid_keywords()), payload)


def test_rejects_reused_sense_key_with_different_lexical_descriptor() -> None:
    first = _valid_keywords()[0]
    second = {
        **first,
        "keyword_id": "KW_other_0001",
        "knowledge_id": "K_other_001",
        "query_lemma": "testament",
    }
    candidates = [
        {"candidate_id": "DEMO", "items": [{"knowledge_id": "K_demo_001", "keywords": [first]}]},
        {"candidate_id": "OTHER", "items": [{"knowledge_id": "K_other_001", "keywords": [second]}]},
    ]

    with pytest.raises(ValueError, match="sense_key"):
        attach_canonical_keywords(candidates)


def test_rejects_time_qualifier_without_temporal_relation_datatype() -> None:
    keywords = _valid_keywords()
    keywords[1]["keyword_kind"] = "qualifier"

    with pytest.raises(ValueError, match="temporal_relation"):
        validate_keyword_output(_raw(keywords), _payload())


def test_rejects_same_sense_key_with_different_hint() -> None:
    first = _valid_keywords()[0]
    second = {
        **first,
        "keyword_id": "KW_other_0001",
        "knowledge_id": "K_other_001",
        "sense_hint": "a different description for the same sense key",
    }
    candidates = [
        {"candidate_id": "DEMO", "items": [{"knowledge_id": "K_demo_001", "keywords": [first]}]},
        {"candidate_id": "OTHER", "items": [{"knowledge_id": "K_other_001", "keywords": [second]}]},
    ]

    with pytest.raises(ValueError, match="sense_key"):
        attach_canonical_keywords(candidates)
