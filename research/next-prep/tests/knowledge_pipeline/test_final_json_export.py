from __future__ import annotations

import hashlib
import json
from pathlib import Path

from knowledge_pipeline.cli import build_parser
from knowledge_pipeline.export import build_turn_grouped_export, write_turn_grouped_export


def _write(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _fixtures(tmp_path: Path) -> tuple[Path, Path, Path]:
    source = tmp_path / "KE-test.json"
    final = tmp_path / "final-knowledge.json"
    keywords = tmp_path / "keyword-pass.json"
    _write(source, {
        "candidates": [{
            "id": "CAND",
            "source": "fixture",
            "turns": [
                {"user": "I like coffee.", "agent": "Noted."},
                {"user": "Actually tea.", "agent": "Updated."},
            ],
        }]
    })
    _write(final, {
        "schema_version": "final-knowledge-v1",
        "active_ids": ["K_user", "K_agent", "D_cross"],
        "counts": {"active": 3, "corrected": 1},
        "records": [
            {
                "knowledge": {
                    "knowledge_id": "K_user", "candidate_id": "CAND", "source_status": "user_reported",
                    "statement": "User likes tea.", "evidence": [{"turn_index": 1, "message": "user", "quote": "tea"}],
                },
                "projection": {"status": "active", "stage": "turn", "source_turn": 1},
            },
            {
                "knowledge": {
                    "knowledge_id": "K_agent", "candidate_id": "CAND", "source_status": "agent_generated",
                    "statement": "Agent noted the preference.", "evidence": [{"turn_index": 0, "message": "agent", "quote": "Noted"}],
                },
                "projection": {"status": "active", "stage": "turn", "source_turn": 0},
            },
            {
                "knowledge": {
                    "knowledge_id": "D_cross", "candidate_id": "CAND", "source_status": "user_reported",
                    "statement": "Tea replaces coffee.",
                    "evidence": [
                        {"turn_index": 0, "message": "user", "quote": "coffee"},
                        {"turn_index": 1, "message": "user", "quote": "tea"},
                    ],
                },
                "projection": {"status": "active", "stage": "dialogue", "source_turn": 0},
            },
            {
                "knowledge": {
                    "knowledge_id": "K_old", "candidate_id": "CAND", "source_status": "user_reported",
                    "statement": "User likes coffee.", "evidence": [{"turn_index": 0, "message": "user", "quote": "coffee"}],
                },
                "projection": {"status": "corrected", "stage": "turn", "source_turn": 0, "replacement_id": "D_cross"},
            },
        ],
    })
    _write(keywords, {
        "schema_version": "keyword-pass-v2",
        "final_knowledge_sha256": hashlib.sha256(final.read_bytes()).hexdigest(),
        "canonical_keywords": [
            {"canonical_id": "CK_tea", "keyword_kind": "lexical", "query_lemma": "tea"},
            {"canonical_id": "CK_preference", "keyword_kind": "lexical", "query_lemma": "preference"},
            {"canonical_id": "CK_replace", "keyword_kind": "lexical", "query_lemma": "replace"},
        ],
        "candidates": [{
            "candidate_id": "CAND",
            "items": [
                {"knowledge_id": "K_user", "keywords": [{"keyword_id": "KW_1", "canonical_id": "CK_tea", "surface": "tea"}], "no_keyword_reason": None},
                {"knowledge_id": "K_agent", "keywords": [{"keyword_id": "KW_2", "canonical_id": "CK_preference", "surface": "preference"}], "no_keyword_reason": None},
                {"knowledge_id": "D_cross", "keywords": [{"keyword_id": "KW_3", "canonical_id": "CK_replace", "surface": "replaces"}], "no_keyword_reason": None},
            ],
        }],
    })
    return source, final, keywords


def test_export_groups_turn_knowledge_and_keywords_by_role(tmp_path: Path) -> None:
    source, final, keywords = _fixtures(tmp_path)
    result = build_turn_grouped_export(source, final, keywords)
    first, second = result

    assert first["原始文本"] == {"user": "I like coffee.", "agent": "Noted."}
    assert [item["statement"] for item in first["知识"]["agent"]] == ["Agent noted the preference."]
    assert first["关键词"]["agent"] == [[{"surface": "preference"}]]
    assert [item["statement"] for item in second["知识"]["user"]] == [
        "Tea replaces coffee.",
        "User likes tea.",
    ]
    assert len(second["关键词"]["user"]) == 2


def test_export_keeps_cross_turn_knowledge_and_history_without_duplication(tmp_path: Path) -> None:
    source, final, keywords = _fixtures(tmp_path)
    result = build_turn_grouped_export(source, final, keywords)

    statements = [
        item["statement"]
        for turn in result
        for role in ("user", "agent")
        for item in turn["知识"][role]
    ]
    assert sorted(statements) == [
        "Agent noted the preference.",
        "Tea replaces coffee.",
        "User likes tea.",
    ]
    assert "Tea replaces coffee." not in [item["statement"] for item in result[0]["知识"]["user"]]
    assert "Tea replaces coffee." in [item["statement"] for item in result[1]["知识"]["user"]]


def test_export_contains_only_original_text_knowledge_and_keywords(tmp_path: Path) -> None:
    source, final, keywords = _fixtures(tmp_path)
    result = build_turn_grouped_export(source, final, keywords)
    turn = result[0]

    assert isinstance(result, list)
    assert set(turn) == {"原始文本", "知识", "关键词"}
    assert set(turn["原始文本"]) == {"user", "agent"}
    assert set(turn["知识"]) == {"user", "agent"}
    assert set(turn["关键词"]) == {"user", "agent"}
    assert "projection" not in turn["知识"]["agent"][0]
    assert "id" not in turn["知识"]["agent"][0]
    assert set(turn["知识"]["agent"][0]) == {
        "statement", "subject", "predicate", "object", "qualifiers",
    }
    keyword = turn["关键词"]["agent"][0][0]
    assert set(keyword) <= {
        "surface", "normalized_zh", "lemma", "kind", "type", "role", "value", "datatype", "unit",
    }


def test_write_turn_grouped_export_is_deterministic(tmp_path: Path) -> None:
    source, final, keywords = _fixtures(tmp_path)
    output = tmp_path / "final.json"

    first = write_turn_grouped_export(source, final, keywords, output)
    first_bytes = output.read_bytes()
    second = write_turn_grouped_export(source, final, keywords, output)

    assert first == second == hashlib.sha256(first_bytes).hexdigest()
    assert output.read_bytes() == first_bytes
    assert not output.with_name("final.json.new").exists()


def test_cli_registers_final_json_export_defaults() -> None:
    args = build_parser().parse_args(["export-final-json"])

    assert args.source == Path("data/gold-candidates/KE-test.json")
    assert args.final_knowledge == Path("knowledge-extraction/final-knowledge.json")
    assert args.keyword_pass == Path(
        "knowledge-extraction/keyword-pass-v3/keyword-pass.json"
    )
    assert args.output == Path("knowledge-extraction/KE-knowledge-keywords.json")
