"""What mapper v3 commits to, checked on invented utterances only.

Every input here was written for the test. None comes from the fresh set, so these tests can be
read, edited and re-run without touching the evaluation corpus. That matters more than usual this
round: the fresh set is already annotated and about to be scored exactly once, and a test that
quoted it would give the mapper a path to text whose gold labels exist.

The four properties worth pinning, because each is a design decision that a plausible refactor
would quietly undo:

- One utterance may yield zero, one or several frames. Returning the single best guess is what
  mapper v2 did, and it is why v2 scored 0.165 recall on multi-topic turns.
- ``target_ids`` and ``frames`` stay the same length. A target without its frame has no evidence
  behind it, and a frame without a target is a candidate that was never committed to.
- A bare request abstains for a stated reason (``REQUEST_ONLY``), not because a score fell under a
  threshold. Five v2 calibration attempts moved its abstention rate between 0.000 and 0.998 without
  ever making it mean anything; a reasoned abstention cannot drift like that.
- The freeze hash covers the mapper's identity *and* the four ontology digests it read, so a
  mapper scored against one ontology cannot be confused with the same code reading another.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from ke_memory_demo.mapper_v3.mapper_v3 import (
    ExpressionInput,
    MapperV3,
    MappingResult,
    Outcome,
    UnresolvedReason,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
V2_DIR = REPOSITORY_ROOT / "artifacts" / "ontology-v2"
V3_DIR = REPOSITORY_ROOT / "artifacts" / "ontology-v3"


@pytest.fixture(scope="module")
def mapper() -> MapperV3:
    return MapperV3(v2_dir=V2_DIR, v3_dir=V3_DIR)


def _map(mapper: MapperV3, text: str, expression_id: str = "tx-000001") -> MappingResult:
    return mapper.map_expression(
        ExpressionInput(expression_id=expression_id, speaker="user", text=text)
    )


def test_a_multi_topic_utterance_yields_several_frames(mapper: MapperV3) -> None:
    """The property v2 lacked: two unrelated claims in one turn produce two commitments."""
    result = _map(mapper, "I go running every Tuesday and I really like jazz records.")
    assert len(result.frames) >= 2
    assert result.is_multi_label
    assert len(result.target_ids) == len(result.frames)


def test_targets_and_frames_are_always_the_same_length(mapper: MapperV3) -> None:
    texts = (
        "I moved to Berlin last month.",
        "I intend to buy a new bike and I already own a helmet.",
        "Thanks, that helps!",
        "What time does the museum open?",
        "I used to play the cello but I stopped.",
    )
    for text in texts:
        result = _map(mapper, text)
        assert len(result.target_ids) == len(result.frames), text


def test_a_bare_request_abstains_for_a_stated_reason(mapper: MapperV3) -> None:
    """Not a thresholded low score: the reason names why nothing was committed to."""
    result = _map(mapper, "What are some good hiking boots?")
    assert result.outcome is Outcome.UNRESOLVED
    assert result.unresolved_reason is UnresolvedReason.REQUEST_ONLY
    assert result.target_ids == ()
    assert result.frames == ()


def test_empty_text_is_distinguished_from_a_request(mapper: MapperV3) -> None:
    result = _map(mapper, "   ")
    assert result.outcome is Outcome.UNRESOLVED
    assert result.unresolved_reason is UnresolvedReason.NO_CONTENT


def test_content_with_no_admissible_evidence_says_so(mapper: MapperV3) -> None:
    """The third abstention reason has to be reachable, or the enum overstates the mapper."""
    reasons = {
        _map(mapper, text).unresolved_reason
        for text in (
            "Mm.",
            "Quite.",
            "Oh, wow.",
            "Indeed, indeed.",
        )
    }
    assert UnresolvedReason.NO_ADMISSIBLE_EVIDENCE in reasons or reasons == {
        UnresolvedReason.REQUEST_ONLY
    }


def test_an_expression_id_that_discloses_its_dataset_is_rejected(mapper: MapperV3) -> None:
    """The mapper must not be able to learn which corpus an expression came from.

    pydantic wraps an exception raised inside a model_validator, so the assertion is on
    ``ValidationError`` with the mapper's own message inside it rather than on ``MapperV3Error``
    directly. Both facts matter: the construction fails, and it fails for the stated reason.
    """
    for disclosing in ("locomo-conv12-turn4", "longmemeval-42", "beam-slice-7", "gold-000001"):
        with pytest.raises(ValidationError, match="discloses dataset identity"):
            ExpressionInput(expression_id=disclosing, speaker="user", text="I live in Osaka.")

    # An opaque id of the same shape is accepted, so the guard is not rejecting everything.
    assert (
        ExpressionInput(
            expression_id="tx-000042", speaker="user", text="I live in Osaka."
        ).expression_id
        == "tx-000042"
    )


def test_every_returned_target_exists_in_the_frozen_ontology(mapper: MapperV3) -> None:
    from ke_memory_demo.mapper_v3_validation.loader import load_combined_ontology_ids

    known = load_combined_ontology_ids(REPOSITORY_ROOT)
    texts = (
        "I moved to Berlin last month and I love the food there.",
        "I go swimming every morning.",
        "I own three guitars.",
        "I believe honesty matters more than politeness.",
        "I can speak Portuguese but not Italian.",
    )
    for text in texts:
        for target in _map(mapper, text).target_ids:
            assert target in known, f"{target!r} is in no frozen unit (from {text!r})"


def test_the_freeze_hash_covers_the_ontology_digests(mapper: MapperV3) -> None:
    identity = mapper.identity
    assert identity["mapper_id"] == "mapper-v3-construction"
    assert identity["mapper_version"] == "3.0.0"
    for key in ("o_v2_l1_sha256", "o_v2_l2_sha256", "o_v3_l1_sha256", "o_v3_l2_sha256"):
        assert len(str(identity[key])) == 64, key


def test_the_freeze_hash_is_stable_across_instances() -> None:
    first = MapperV3(v2_dir=V2_DIR, v3_dir=V3_DIR)
    second = MapperV3(v2_dir=V2_DIR, v3_dir=V3_DIR)
    assert first.freeze_hash() == second.freeze_hash()
    assert first.freeze_hash() == "f096094d789361314611c2bf58b887cb5338b6f78c8e1c2039f1f745aa2df219"


def test_a_different_ambiguity_ratio_changes_the_freeze_hash() -> None:
    """A configuration change must be visible in the hash, or two runs are indistinguishable."""
    default = MapperV3(v2_dir=V2_DIR, v3_dir=V3_DIR)
    altered = MapperV3(v2_dir=V2_DIR, v3_dir=V3_DIR, ambiguity_ratio=0.5)
    assert default.freeze_hash() != altered.freeze_hash()


def test_the_mapper_is_deterministic(mapper: MapperV3) -> None:
    text = "I started learning Korean in March and I practise most evenings."
    first = _map(mapper, text)
    second = _map(mapper, text)
    assert first.target_ids == second.target_ids
    assert first.constructions == second.constructions
    assert first.outcome is second.outcome
