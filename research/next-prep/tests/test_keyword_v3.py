from __future__ import annotations

import json

import pytest

from knowledge_pipeline.cli import build_parser
from knowledge_pipeline.export import _display_keyword_item
from knowledge_pipeline.keyword_v3 import (
    _verify_wordnet_mapping,
    attach_canonical_keywords_v3,
    prepare_keyword_v3_payloads,
    validate_keyword_v3_batch,
    validate_keyword_v3_output,
)
from knowledge_pipeline.models import AtomicKeywordDraft


WORDNET_DIR = "knowledge-extraction/resources/nltk_data"


def _knowledge() -> dict[str, object]:
    return {
        "knowledge_id": "K_demo_001",
        "candidate_id": "DEMO",
        "statement": "用户计划在休假前联系事务所合伙人，并安排工作交接。",
        "subject": "用户",
        "predicate": "计划联系并安排",
        "object": "事务所合伙人与工作交接",
        "qualifiers": {
            "modality": "planned",
            "polarity": "positive",
            "temporal": ["休假前"],
            "conditions": [],
            "scope": [],
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
    keyword: str,
    keyword_type: str,
    semantic_role: str,
    source_field: str,
    wordnet_synset: str | None,
    wordnet_lemma: str | None,
    wordnet_pos: str | None,
) -> dict[str, object]:
    return {
        "keyword_id": f"KW_demo_{index:04d}",
        "knowledge_id": "K_demo_001",
        "surface": surface,
        "keyword": keyword,
        "keyword_type": keyword_type,
        "semantic_role": semantic_role,
        "source_field": source_field,
        "wordnet_synset": wordnet_synset,
        "wordnet_lemma": wordnet_lemma,
        "wordnet_pos": wordnet_pos,
        "mapping_confidence": 1.0 if wordnet_synset else None,
    }


def _valid_keywords() -> list[dict[str, object]]:
    return [
        _keyword(
            1,
            surface="休假",
            keyword="休假",
            keyword_type="event",
            semantic_role="time",
            source_field="qualifiers.temporal",
            wordnet_synset="leave.n.01",
            wordnet_lemma="leave",
            wordnet_pos="n",
        ),
        _keyword(
            2,
            surface="合伙人",
            keyword="合伙人",
            keyword_type="entity",
            semantic_role="object",
            source_field="object",
            wordnet_synset="partner.n.03",
            wordnet_lemma="partner",
            wordnet_pos="n",
        ),
        _keyword(
            3,
            surface="工作交接",
            keyword="工作交接",
            keyword_type="event",
            semantic_role="object",
            source_field="object",
            wordnet_synset=None,
            wordnet_lemma=None,
            wordnet_pos=None,
        ),
    ]


def _raw(keywords: list[dict[str, object]]) -> dict[str, object]:
    return {
        "candidate_id": "DEMO",
        "items": [{"knowledge_id": "K_demo_001", "keywords": keywords}],
    }


def test_accepts_real_wordnet_and_unmapped_atomic_keywords() -> None:
    result = validate_keyword_v3_output(_raw(_valid_keywords()), _payload(), WORDNET_DIR)

    assert len(result["items"][0]["keywords"]) == 3


def test_rejects_unknown_wordnet_synset() -> None:
    keywords = _valid_keywords()
    keywords[0]["wordnet_synset"] = "leave.n.99"

    with pytest.raises(ValueError, match="WordNet synset"):
        validate_keyword_v3_output(_raw(keywords), _payload(), WORDNET_DIR)


def test_rejects_lemma_not_in_wordnet_synset() -> None:
    keywords = _valid_keywords()
    keywords[0]["wordnet_lemma"] = "vacation"

    with pytest.raises(ValueError, match="WordNet lemma"):
        validate_keyword_v3_output(_raw(keywords), _payload(), WORDNET_DIR)


def test_rejects_partial_wordnet_mapping() -> None:
    keywords = _valid_keywords()
    keywords[0]["wordnet_lemma"] = None

    with pytest.raises(ValueError, match="mapping fields"):
        validate_keyword_v3_output(_raw(keywords), _payload(), WORDNET_DIR)


@pytest.mark.parametrize(
    "keyword",
    [
        "如果律师批准该草案就联系合伙人",
        "应该提前完成任务并且安排交接",
        "联系事务所合伙人争取工作分派的完整计划",
    ],
)
def test_rejects_clause_or_long_phrase(keyword: str) -> None:
    keywords = _valid_keywords()
    keywords[2]["keyword"] = keyword

    with pytest.raises(ValueError, match="atomic keyword"):
        validate_keyword_v3_output(_raw(keywords), _payload(), WORDNET_DIR)


def test_rejects_untraceable_surface() -> None:
    keywords = _valid_keywords()
    keywords[0]["surface"] = "年假"

    with pytest.raises(ValueError, match="traceable"):
        validate_keyword_v3_output(_raw(keywords), _payload(), WORDNET_DIR)


def test_canonicalizes_mapped_synonyms_by_synset() -> None:
    first = _valid_keywords()[0]
    second = {
        **first,
        "keyword_id": "KW_other_0001",
        "knowledge_id": "K_other_001",
        "surface": "准假",
        "keyword": "准假",
    }
    candidates = [
        {"candidate_id": "DEMO", "items": [{"knowledge_id": "K_demo_001", "keywords": [first]}]},
        {"candidate_id": "OTHER", "items": [{"knowledge_id": "K_other_001", "keywords": [second]}]},
    ]

    registry = attach_canonical_keywords_v3(candidates)

    assert len(registry) == 1
    assert first["canonical_id"] == second["canonical_id"]


def test_prepares_and_validates_a_complete_v3_batch(tmp_path) -> None:
    final_path = tmp_path / "final-knowledge.json"
    final_path.write_text(
        json.dumps(
            {
                "active_ids": ["K_demo_001"],
                "records": [
                    {
                        "knowledge": _knowledge(),
                        "projection": {"status": "active"},
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    prompt_path = tmp_path / "prompt.md"
    prompt_path.write_text(
        "\n".join(
            [
                "## Input Boundary",
                "## Atomic Keyword Rules",
                "## WordNet Mapping Rules",
                "## Evidence Rules",
                "## Forbidden Behavior",
                "## Final Self-Check",
            ]
        ),
        encoding="utf-8",
    )
    prepared = tmp_path / "prepared"
    manifest_path = prepare_keyword_v3_payloads(final_path, prepared, prompt_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    payload = json.loads((prepared / "payloads" / "0000.json").read_text(encoding="utf-8"))
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    raw = _raw(_valid_keywords())
    for index, keyword in enumerate(raw["items"][0]["keywords"], start=1):
        keyword["keyword_id"] = f"{payload['keyword_id_prefix']}{index:04d}"
    (raw_dir / "0000.json").write_text(
        json.dumps(raw, ensure_ascii=False),
        encoding="utf-8",
    )
    output = tmp_path / "keyword-pass-v3.json"

    validate_keyword_v3_batch(manifest_path, raw_dir, output, WORDNET_DIR)
    aggregate = json.loads(output.read_text(encoding="utf-8"))

    assert manifest["prompt_version"] == "knowledge-keyword-extraction-v3"
    assert payload["active_knowledge"] == [_knowledge() | {"projection": {"status": "active"}}]
    assert aggregate["schema_version"] == "keyword-pass-v3"
    assert aggregate["active_knowledge_count"] == 1
    assert len(aggregate["canonical_keywords"]) == 3


def test_display_contains_only_keyword_and_optional_wordnet_mapping() -> None:
    displayed = _display_keyword_item(
        {
            "knowledge_id": "K_demo_001",
            "keywords": _valid_keywords(),
        }
    )

    assert displayed == {
        "knowledge_id": "K_demo_001",
        "keywords": [
            {
                "keyword": "休假",
                "wordnet": {"synset": "leave.n.01", "lemma": "leave", "pos": "n"},
            },
            {
                "keyword": "合伙人",
                "wordnet": {"synset": "partner.n.03", "lemma": "partner", "pos": "n"},
            },
            {"keyword": "工作交接"},
        ],
    }


def test_cli_exposes_v3_prepare_and_validate_commands() -> None:
    parser = build_parser()

    prepare = parser.parse_args(["prepare-keywords-v3"])
    validate = parser.parse_args(["validate-keywords-v3"])

    assert str(prepare.output_dir).endswith("knowledge-extraction\\keyword-pass-v3\\prepared")
    assert str(validate.wordnet_dir).endswith("knowledge-extraction\\resources\\nltk_data")


def test_accepts_thousands_separator_in_quantity_keyword() -> None:
    keyword = AtomicKeywordDraft.model_validate(
        {
            "keyword_id": "KW_demo_0001",
            "knowledge_id": "K_demo_001",
            "surface": "2,677美元",
            "keyword": "2,677美元",
            "keyword_type": "quantity",
            "semantic_role": "value",
            "source_field": "object",
            "wordnet_synset": None,
            "wordnet_lemma": None,
            "wordnet_pos": None,
            "mapping_confidence": None,
        }
    )

    assert keyword.keyword == "2,677美元"


def test_accepts_atomic_date_range_keyword() -> None:
    keyword = AtomicKeywordDraft.model_validate(
        {
            "keyword_id": "KW_demo_0001",
            "knowledge_id": "K_demo_001",
            "surface": "12 月 15 日到 12 月 26 日",
            "keyword": "12月15日至12月26日",
            "keyword_type": "time",
            "semantic_role": "time",
            "source_field": "object",
            "wordnet_synset": None,
            "wordnet_lemma": None,
            "wordnet_pos": None,
            "mapping_confidence": None,
        }
    )

    assert keyword.keyword == "12月15日至12月26日"


def test_wordnet_alias_resolves_to_canonical_synset_name() -> None:
    canonical = _verify_wordnet_mapping(
        {
            "wordnet_synset": "discuss.v.01",
            "wordnet_lemma": "discuss",
            "wordnet_pos": "v",
        },
        WORDNET_DIR,
    )

    assert canonical == "discourse.v.01"
