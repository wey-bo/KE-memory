"""Tests for mapper v2, and for the calibration failures that shaped it.

Most of this file records mechanisms rather than protecting a score. The repair attempt did not
succeed: abstention moved 0.098, 0.073, 0.998, 0.000, 0.405, 0.125 across five calibrations without
ever getting correct short mappings and correct abstentions right at once. Each test below pins one
of the reasons why, so a later attempt does not rediscover them.

None of these assertions is tuned against the retired 18-case probe. They check that a mechanism
behaves as described, not that a case set passes.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from ke_memory_demo.mapper_v1.mapper import (
    Layer,
    MapperInput,
    Resolution,
    load_frozen_ontology,
)
from ke_memory_demo.mapper_v2.mapper import (
    CONVERSATIONAL_FILLER,
    MapperV2,
    protected_alias_terms,
    STOPWORDS,
    assert_no_correction_gate,
    terms,
)

ONTOLOGY_DIR = Path(__file__).resolve().parents[3] / "artifacts" / "ontology-v1"
MAPPER_SOURCE = (
    Path(__file__).resolve().parents[3]
    / "src"
    / "ke_memory_demo"
    / "mapper_v2"
    / "mapper.py"
)

requires_ontology = pytest.mark.skipif(
    not (ONTOLOGY_DIR / "o_l1.json").is_file(),
    reason="the frozen ontology artifact is not present",
)


def _mapper(**kwargs: object) -> MapperV2:
    return MapperV2(load_frozen_ontology(ONTOLOGY_DIR), **kwargs)  # type: ignore[arg-type]


def test_blindness_is_inherited_unchanged() -> None:
    """v2 changes scoring, not what a mapper may see."""
    assert set(MapperInput.model_fields) == {"expression_id", "speaker", "text"}
    with pytest.raises(Exception, match="discloses dataset identity"):
        MapperInput(expression_id="BEAM-100K-C001", speaker="user", text="hello")


def test_no_correction_gate_is_defined() -> None:
    assert_no_correction_gate(MAPPER_SOURCE.read_text(encoding="utf-8"))
    tree = ast.parse(MAPPER_SOURCE.read_text(encoding="utf-8"))
    defined = {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    assert "fix_mapping" not in defined
    assert "override_sense" not in defined


def test_an_abstention_must_state_why() -> None:
    """An unexplained abstain cannot be diagnosed, so the record requires a reason."""
    from pydantic import ValidationError

    from ke_memory_demo.mapper_v2.mapper import MappingRecordV2

    with pytest.raises(ValidationError, match="must record why it declined"):
        MappingRecordV2(
            expression_id="expr-1",
            layer=Layer.L1,
            candidates=(),
            resolution=Resolution.UNRESOLVED,
        )


@requires_ontology
def test_ontologyprotected_alias_terms_survive_stopword_removal() -> None:
    """The defect: a fixed stopword list deleted the words the ontology maps with.

    ``like`` is the alias carrying ``l1:predicate.hold_attitude``, so removing it made "I really like
    jazz records" unmappable. Fourteen such collisions exist in the seed ontology.
    """
    ontology = load_frozen_ontology(ONTOLOGY_DIR)
    protected = protected_alias_terms(ontology.items_for(Layer.L1))
    assert "like" in protected
    assert "like" in STOPWORDS  # it is a stopword and still must survive
    assert "like" in terms("I really like jazz records", protected=protected)
    # Without protection the term is gone, which is what broke the mapping.
    assert "like" not in terms("I really like jazz records")


@requires_ontology
def test_only_a_stopword_that_is_itself_an_alias_is_protected() -> None:
    """Protecting every alias word drove abstention to zero.

    Two rules were tried and rejected. Protecting any word appearing in an alias kept ``the`` and
    ``and``, which ride inside phrases such as "make an appointment" and match nearly every turn.
    Counting items per word still protected 30 terms including ``the``, because a common word can
    appear in few aliases and remain ambient.

    What holds is whether the stopword *is* the whole alias: ``like`` stands alone as an alias of
    hold_attitude, while ``the`` only ever appears inside a longer phrase.
    """
    ontology = load_frozen_ontology(ONTOLOGY_DIR)
    protected = protected_alias_terms(ontology.items_for(Layer.L1))
    assert "like" in protected
    for ambient in ("the", "and", "for", "about", "make", "than", "please"):
        assert ambient not in protected, ambient


@requires_ontology
def test_a_protected_stopword_is_matchable_but_never_decisive() -> None:
    """Counting protected stopwords as decisive put 74 percent of turns in "ambiguous".

    ``and``, ``for`` and ``every`` satisfied the evidence test on their own, which reproduced v1's
    degeneracy from the other direction.
    """
    mapper = _mapper()
    record = mapper.map_expression(
        MapperInput(expression_id="expr-1", speaker="user", text="please and for every"),
        Layer.L1,
    )
    for candidate in record.candidates:
        assert not (set(candidate.discriminative_terms) & STOPWORDS)


@requires_ontology
def test_ranking_prefers_decisive_evidence_over_a_higher_score() -> None:
    """The last mechanism found.

    ``please`` scored above ``cancel`` on "please cancel my flight reservation". Since the abstain
    check inspects only the top candidate, the real alias was buried and the whole mapping was
    discarded as generic.
    """
    mapper = _mapper()
    record = mapper.map_expression(
        MapperInput(
            expression_id="expr-1", speaker="user", text="Please cancel my flight reservation"
        ),
        Layer.L1,
    )
    assert record.resolution is not Resolution.UNRESOLVED
    assert record.candidates[0].discriminative_terms
    assert record.top_ontology_id == "l1:predicate.change_arrangement"


@requires_ontology
def test_conversational_filler_is_weighted_down_not_merely_excluded() -> None:
    """A pile of filler must not clear a threshold that one real term would."""
    mapper = _mapper()
    record = mapper.map_expression(
        MapperInput(
            expression_id="expr-1",
            speaker="user",
            text="the thing is that day was a good time and things went the way people say",
        ),
        Layer.L1,
    )
    assert record.resolution is Resolution.UNRESOLVED
    # The turn is filler by construction, so the filler list must actually cover it. An assertion
    # ending in "or True" cannot fail and was checking nothing.
    observed = terms("the thing is that day was a good time and things went the way people say")
    assert observed
    assert observed <= CONVERSATIONAL_FILLER | STOPWORDS


@requires_ontology
def test_an_utterance_with_no_content_terms_abstains_with_a_named_reason() -> None:
    mapper = _mapper()
    record = mapper.map_expression(
        MapperInput(expression_id="expr-1", speaker="user", text="!!! ..."),
        Layer.L1,
    )
    assert record.resolution is Resolution.UNRESOLVED
    assert record.abstain_reason is not None


@requires_ontology
def test_score_is_normalised_so_a_threshold_can_be_reasoned_about() -> None:
    """A raw IDF sum has no fixed range; an absolute floor against it is uncalibratable.

    Measured on discovery turns the raw sums reached the fifth percentile at 4.51, so a 0.35 floor
    rejected nothing whatsoever.
    """
    mapper = _mapper()
    record = mapper.map_expression(
        MapperInput(
            expression_id="expr-1", speaker="user", text="I booked a table for Friday evening"
        ),
        Layer.L1,
    )
    for candidate in record.candidates:
        assert 0.0 <= candidate.score <= 1.0


@requires_ontology
def test_the_repair_is_recorded_as_incomplete() -> None:
    """The honest state: abstention improved marginally and the degeneracy is not resolved.

    Asserting a target abstention rate here would be fitting the very probe the sequence retired, so
    the test pins the plan's own admission instead.
    """
    import json

    plan = json.loads(
        (
            Path(__file__).resolve().parents[3] / "docs" / "plans" / "benchmark-plan-v2.1.json"
        ).read_text(encoding="utf-8")
    )
    # Read from mapper_v1.repair_attempt rather than by index into next_sequence: the sequence is
    # renumbered as the plan advances, and an index-based assertion silently checks a different step.
    attempt = plan["program_plan"]["mapper_v1"]["repair_attempt"]
    assert attempt["status"] == "attempted_not_achieved"
    assert "lexical" in attempt["conclusion"]
    assert attempt["recommendation"]
    # The five root causes are the reusable part; losing them would cost more than the attempt did.
    assert len(attempt["root_causes_found"]) >= 5
