from __future__ import annotations

from tools.keol_baseline.export_keol_views import (
    build_assertion_unit_index,
    render_keol_term,
)


def test_render_keol_term_uses_typed_readable_values() -> None:
    term = {
        "term_type": "operator_application",
        "operator_id": "op_works_at",
        "arguments": [
            {
                "role": "input",
                "term": {"term_type": "individual", "id": "person_user"},
            }
        ],
    }

    rendered = render_keol_term(
        term,
        operators={"op_works_at": "works_at"},
        individuals={"person_user": "用户"},
        concepts={},
    )

    assert rendered == 'works_at(Individual("用户"))'


def test_build_assertion_unit_index_uses_evidence_source_file() -> None:
    assertions = [
        {"id": "a1", "evidence_ids": ["e1"]},
        {"id": "a2", "evidence_ids": ["e2", "e3"]},
    ]
    evidence = [
        {
            "id": "e1",
            "source_file": "artifacts/keol-baseline/input/turns/cand-001__turn-001.txt",
        },
        {
            "id": "e2",
            "source_file": "artifacts/keol-baseline/input/turns/cand-001__turn-002.txt",
        },
        {
            "id": "e3",
            "source_file": "artifacts/keol-baseline/input/turns/cand-001__turn-003.txt",
        },
    ]

    index = build_assertion_unit_index(assertions, evidence)

    assert index == {
        "cand-001__turn-001": ["a1"],
        "cand-001__turn-002": ["a2"],
        "cand-001__turn-003": ["a2"],
    }
