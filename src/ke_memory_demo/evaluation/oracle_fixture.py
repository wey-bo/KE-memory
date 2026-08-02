"""Synthetic fixture carrying genuine per-layer gold.

The 32-item regression slice has no extraction, mapping, L2 or query-plan annotation. A
review refused the previous attempt to reuse its evidence references as a stand-in for all
four, so the substitution mechanism is validated here instead, on cases small enough to
annotate honestly and constructed so each layer's gold differs from the fixture's own
output. Without that difference a substitution could be effective and still look inert.

Each case is built so exactly one thing is wrong at each layer:

- the fixture extracts a distractor turn that extraction gold omits
- the fixture maps to a lexical id where mapping gold names a canonical concept
- the fixture groups by shared term where L2 gold declares a real abstraction
- the fixture plans from question words where plan gold requests a canonical id
"""

from __future__ import annotations

from .channels import (
    BenchmarkId,
    BenchmarkQuestion,
    GoldChannel,
    GoldLabels,
    LoadedBenchmark,
    MemoryBuildInput,
    PublicConversation,
    PublicSession,
    PublicTurn,
    QuestionChannel,
)
from .layer_gold import (
    ExtractionGoldUnit,
    L2GoldAbstraction,
    LayerGold,
    LayerGoldBundle,
    MappingGoldEntry,
    QueryPlanGold,
)

FIXTURE_ID = "oracle-mechanism-fixture-v1"


def _turn(handle: str, speaker: str, text: str) -> PublicTurn:
    return PublicTurn(
        evidence_handle=handle,
        speaker=speaker,
        text=text,
        approximate_tokens=max(1, (len(text) + 3) // 4),
    )


def build_fixture() -> tuple[LoadedBenchmark, LayerGoldBundle]:
    """A two-question fixture with per-layer gold for every layer."""
    conversations = (
        PublicConversation(
            conversation_handle="c00000",
            sessions=(
                PublicSession(
                    session_handle="s00000",
                    turns=(
                        _turn("h00000", "user", "I joined Globex as a manager in March."),
                        _turn("h00001", "assistant", "Congratulations on the new role."),
                        _turn("h00002", "user", "I was promoted to senior manager in September."),
                        _turn("h00003", "user", "Unrelated: the weather has been mild lately."),
                    ),
                    metadata={"public_session_ordinal": 0},
                ),
            ),
        ),
        PublicConversation(
            conversation_handle="c00001",
            sessions=(
                PublicSession(
                    session_handle="s00001",
                    turns=(
                        _turn("h00004", "user", "I switched from tea to oat milk coffee."),
                        _turn("h00005", "assistant", "Noted, oat milk it is."),
                        _turn("h00006", "user", "Actually I stopped drinking coffee entirely."),
                    ),
                    metadata={"public_session_ordinal": 0},
                ),
            ),
        ),
    )

    questions = QuestionChannel(
        benchmark=BenchmarkId.REGRESSION_SLICE,
        questions=(
            BenchmarkQuestion(
                question_id="fx-q1",
                conversation_handle="c00000",
                question="What is the current role and employer?",
            ),
            BenchmarkQuestion(
                question_id="fx-q2",
                conversation_handle="c00001",
                question="What does the user drink now?",
            ),
        ),
    )

    gold = GoldChannel(
        benchmark=BenchmarkId.REGRESSION_SLICE,
        labels=(
            GoldLabels(
                question_id="fx-q1",
                conversation_handle="c00000",
                answer="Senior manager at Globex",
                evidence_refs=("h00000", "h00002"),
            ),
            GoldLabels(
                question_id="fx-q2",
                conversation_handle="c00001",
                answer="Nothing; the user stopped drinking coffee",
                # Both turns are required: h5 establishes the preference and h7 supersedes
                # it. Naming only h7 would make the gold evidence set inconsistent with the
                # L2 derivation below, and a fixture that contradicts itself cannot show
                # whether the pipeline is right.
                evidence_refs=("h00004", "h00006"),
            ),
        ),
    )

    bundle = LayerGoldBundle(
        fixture_id=FIXTURE_ID,
        entries=(
            LayerGold(
                question_id="fx-q1",
                # Omits h2 and the h4 distractor, which the fixture extractor keeps.
                extraction=(
                    ExtractionGoldUnit(evidence_handle="h00000", role="agent", predicate="join-01"),
                    ExtractionGoldUnit(evidence_handle="h00002", role="agent", predicate="promote-01"),
                ),
                mapping=(
                    MappingGoldEntry(
                        evidence_handle="h00000", canonical_id="memory:Employment", sense="join.01"
                    ),
                    MappingGoldEntry(
                        evidence_handle="h00002", canonical_id="memory:Employment", sense="promote.01"
                    ),
                ),
                l2=(
                    L2GoldAbstraction(
                        abstraction_id="abs:employment-history",
                        canonical_id="memory:EmploymentHistory",
                        derived_from=("h00000", "h00002"),
                    ),
                ),
                query_plan=QueryPlanGold(
                    question_id="fx-q1",
                    requested_canonical_ids=("memory:EmploymentHistory",),
                    requires_abstraction=True,
                ),
            ),
            LayerGold(
                question_id="fx-q2",
                extraction=(
                    ExtractionGoldUnit(evidence_handle="h00004", role="agent", predicate="prefer-01"),
                    ExtractionGoldUnit(evidence_handle="h00006", role="agent", predicate="stop-01"),
                ),
                mapping=(
                    MappingGoldEntry(
                        evidence_handle="h00004", canonical_id="memory:Preference", sense="prefer.01"
                    ),
                    MappingGoldEntry(
                        evidence_handle="h00006", canonical_id="memory:Preference", sense="cease.01"
                    ),
                ),
                l2=(
                    L2GoldAbstraction(
                        abstraction_id="abs:beverage-preference",
                        canonical_id="memory:PreferenceState",
                        derived_from=("h00004", "h00006"),
                    ),
                ),
                query_plan=QueryPlanGold(
                    question_id="fx-q2",
                    requested_canonical_ids=("memory:PreferenceState",),
                    requires_abstraction=True,
                ),
            ),
        ),
    )

    build_input = MemoryBuildInput(conversations=conversations)
    return (
        LoadedBenchmark(
            benchmark=BenchmarkId.REGRESSION_SLICE,
            build_input=build_input,
            questions=questions,
            gold=gold,
            source_identity={"loader_id": FIXTURE_ID, "loader_version": "3"},
        ),
        bundle,
    )
