from __future__ import annotations

import penman

from tools.amr_pilot.penman_validation import validate_penman


INVENTORY = {"cancel-01", "person", "thing"}


def test_valid_graph_decodes_with_one_top_and_known_frame() -> None:
    result = validate_penman(
        "(c / cancel-01 :ARG0 (p / person) :ARG1 (t / thing) :polarity -)",
        propbank_inventory=INVENTORY,
    )

    assert result.syntax_valid is True
    assert result.is_valid is True
    assert result.graph_count == 1
    assert result.unknown_frames == ()
    assert isinstance(result.graphs[0], penman.Graph)


def test_malformed_graph_is_a_parse_failure() -> None:
    result = validate_penman("(c / cancel-01 :ARG0", propbank_inventory=INVENTORY)

    assert result.syntax_valid is False
    assert result.is_valid is False
    assert result.errors


def test_markdown_fence_is_rejected_without_silent_cleanup() -> None:
    result = validate_penman(
        "```penman\n(c / cancel-01)\n```",
        propbank_inventory=INVENTORY,
    )

    assert result.syntax_valid is False
    assert "Markdown fences are not allowed" in result.errors


def test_missing_instance_triple_is_reported() -> None:
    result = validate_penman(
        "(c :ARG0 (p / person))",
        propbank_inventory=INVENTORY,
    )

    assert result.syntax_valid is True
    assert result.is_valid is False
    assert any("missing an instance triple" in error for error in result.errors)


def test_unbound_core_role_reference_is_reported() -> None:
    result = validate_penman(
        "(c / cancel-01 :ARG0 p :ARG1 (t / thing))",
        propbank_inventory=INVENTORY,
    )

    assert result.syntax_valid is True
    assert result.is_valid is False
    assert any("unbound reference p" in error for error in result.errors)


def test_multiple_top_graphs_are_rejected() -> None:
    result = validate_penman(
        "(c / cancel-01)\n(p / person)",
        propbank_inventory=INVENTORY,
    )

    assert result.syntax_valid is True
    assert result.graph_count == 2
    assert result.is_valid is False
    assert "exactly one graph is required" in result.errors


def test_unknown_propbank_frame_remains_explicit() -> None:
    result = validate_penman("(x / fabricate-99)", propbank_inventory=INVENTORY)

    assert result.syntax_valid is True
    assert result.is_valid is False
    assert result.unknown_frames == ("fabricate-99",)
    assert any("unknown PropBank frame" in error for error in result.errors)


def test_missing_frame_inventory_is_explicit_without_marking_frames_unknown() -> None:
    result = validate_penman("(x / fabricate-99)", propbank_inventory=None)

    assert result.syntax_valid is True
    assert result.is_valid is True
    assert result.frame_inventory_status == "unavailable"
    assert result.unknown_frames == ()
