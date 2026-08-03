"""The candidate ledger, the provenance snapshot and the assembled v2 ontology.

Three things live here because they are three views of the same act of judgement:

- :func:`build_ledger` records every candidate and its disposition, including the rejections and
  the deferrals that remain. A rejection carries as much weight as an acceptance; v1's 25
  rejections are re-examined against the three published sources and 24 of them survive unchanged,
  which is the main thing this ledger has to say. Frequency in a build corpus was the wrong test in
  v1 and is still the wrong test.
- :func:`build_provenance` records what was read, at which digest, and -- new in v2 --
  ``declined_imports``: what each source offered and what was deliberately left behind. Without
  that field the no-bulk-import rule would be unfalsifiable, because a reader could not tell
  restraint from never having looked.
- :func:`build_foundation_ontology_v2` assembles the six units and runs every cross-unit check, so
  a defective ontology fails here rather than reaching disk and being cited.

The eight v1 deferrals are the spine of the ledger. Six are resolved with source evidence and each
resolution names the deferral it settles, which the freeze model then requires to come with a
citation. Two remain deferred, and their reasons are not "no time": ``l2.topic`` still has no
derivation rule in any of the three sources, and ``attribute.contact_channel`` is still an
Individual's identifier however many services declare it.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Final, cast

from .l1_content import build_o_l1
from .l2_content import build_o_l2

from .models import (
    CandidateDecision,
    DecisionLedger,
    Disposition,
    ExternalGrounding,
    ProvenanceSnapshot,
    SourceKind,
    SourceSnapshot,
    UncoveredExpression,
)
from .supersession import SUPERSEDED_VERSION

ONTOLOGY_VERSION: Final[str] = "2.0.0"

# The digests from artifacts/ontology-sources/source-freeze.json, recomputed against the raw
# archives before this build ran. Written here rather than read from that file so that a change to
# the source freeze cannot silently retag this ontology as built from different bytes.
WORDNET_RAW_SHA256: Final[str] = "cbda5ea6eef7f36a97a43d4a75f85e07fccbb4f23657d27b4ccbc93e2646ab59"
PROPBANK_RAW_SHA256: Final[str] = "3a9d4d25d8f29b5f536452630e2dd83823ca230c45a3fabde785df21a21957dd"
SCHEMAORG_RAW_SHA256: Final[str] = (
    "4467fa19edcb1d7fb3c46c0adf3591b7f870c4a60b7838bdb61694fd02864cf6"
)


def _pb(reference: str, gloss: str, role_hint: str | None = None) -> ExternalGrounding:
    return ExternalGrounding(
        source=SourceKind.PROPBANK, reference=reference, gloss=gloss, role_hint=role_hint
    )


def _wn(reference: str, gloss: str) -> ExternalGrounding:
    return ExternalGrounding(source=SourceKind.WORDNET, reference=reference, gloss=gloss)


def _so(reference: str, gloss: str) -> ExternalGrounding:
    return ExternalGrounding(source=SourceKind.SCHEMAORG, reference=reference, gloss=gloss)


def _accept(
    candidate: str,
    item_id: str,
    source: SourceKind,
    reason: str,
    *,
    resolves: str | None = None,
    grounding: tuple[ExternalGrounding, ...] = (),
) -> CandidateDecision:
    return CandidateDecision(
        candidate=candidate,
        disposition=Disposition.ACCEPTED,
        reason=reason,
        source=source,
        accepted_as=item_id,
        resolves_v1_deferral=resolves,
        grounding=grounding,
    )


def _reject(candidate: str, source: SourceKind, reason: str) -> CandidateDecision:
    return CandidateDecision(
        candidate=candidate, disposition=Disposition.REJECTED, reason=reason, source=source
    )


def _defer(candidate: str, source: SourceKind, reason: str) -> CandidateDecision:
    return CandidateDecision(
        candidate=candidate, disposition=Disposition.DEFERRED, reason=reason, source=source
    )


# --- Acceptances that are new in v2 ------------------------------------------------------
#
# Forty-five items v1 did not have. Six of them name a v1 deferral they settle, and the freeze model
# then requires each of those to carry a resolvable citation -- so "the source debt is paid" is a
# list a reviewer can walk rather than a claim.
_NEW_ACCEPTED: Final[tuple[CandidateDecision, ...]] = (
    _accept(
        "role.cause",
        "l1:role.cause",
        SourceKind.PROPBANK,
        "v1 deferred this on a single tau-bench attestation (cancel_pending_order's two-value "
        "reason) and said PropBank would settle it. PropBank tags 285 roles CAU across 278 "
        "distinct lemmas, and cause.01's own ARG0 carries the tag, so the position is general "
        "rather than one tool's parameter",
        resolves="role.cause",
        grounding=(
            _pb("cause.01", "impelled action", "ARG0 CAU forcer, causer"),
            _pb("plan.01", "expect (roleset name)", "ARG2 CAU grounds for planning"),
        ),
    ),
    _accept(
        "role.duration",
        "l1:role.duration",
        SourceKind.PROPBANK,
        "v1 deferred this because duration was derivable from boundary pairs but never expressed "
        "directly, and it lacked a measurement construct. PropBank has a roleset whose whole sense "
        "is duration (last.01, aliased have-duration), SGD declares three direct duration slots "
        "this build found (approximate_ride_duration, number_of_days, wait_time), and schema.org "
        "types Duration as a Quantity",
        resolves="role.duration",
        grounding=(
            _pb("last.01", "extend for some period of time; duration", "ARG2 VSP period of time"),
            _so("schema:duration", "the duration of the item in ISO 8601 duration format"),
        ),
    ),
    _accept(
        "modality.hypothesis",
        "l1:modality.hypothesis",
        SourceKind.PROPBANK,
        "v1 deferred this because no build corpus attested it and admitting it on the strength of "
        "domain.Modality.HYPOTHESIS would be inventing coverage. PropBank distinguishes supposition "
        "from belief lexically across three rolesets (suppose.01, hypothesize.01, imagine.01), "
        "which is attestation in the reference frame set rather than in this project's enum",
        resolves="modality.hypothesis",
        grounding=(
            _pb("hypothesize.01", "make an educated guess", "ARG1 PPT hypothesis"),
            _pb("suppose.01", "think, assume", "ARG1 PPT thing thought about"),
            _wn(
                "n#05888929",
                "hypothesis, possibility, theory: a tentative insight, not yet verified",
            ),
        ),
    ),
    _accept(
        "modality.question",
        "l1:modality.question",
        SourceKind.PROPBANK,
        "v1 deferred this correctly: SGD's REQUEST is a speech act, not an assertion carrying "
        "question modality, and it left open whether a question is ever remembered content. "
        "PropBank answers it -- wonder.01 'think about, ponder' has no hearer position while "
        "ask.01 has ARG2 GOL hearer, so an unresolved question is a mental state independent of "
        "the act of asking. The 33612 REQUEST acts remain rejected as content",
        resolves="modality.question",
        grounding=(
            _pb("wonder.01", "think about, ponder", "ARG1 PAG thought"),
            _wn("n#07193596", "question, inquiry, query: an instance of questioning"),
        ),
    ),
    _accept(
        "l2.social_relationship",
        "l2:abstraction.relationship",
        SourceKind.MSC_PERSONAS,
        "v1 called this the largest known gap in O_L2 and deferred it because persona sentences "
        "are unannotated, so any inventory would be guessed. This build measures 4647 relationship "
        "mentions concentrated in four families (descent kin 3088, partnership 738, friendship 485, "
        "lateral kin 311), and schema.org supplies the symmetry distinction between knows and "
        "follows, so the shape is taken from the literature and the families from measurement",
        resolves="l2.social_relationship",
        grounding=(
            _so("schema:knows", "the most generic bi-directional social/work relation"),
            _so(
                "schema:Role", "represents additional information about a relationship or property"
            ),
        ),
    ),
    _accept(
        "l2.decision_with_rationale",
        "l1:role.cause",
        SourceKind.PROPBANK,
        "v1 deferred a decision-with-rationale type because SELECT and REQUEST_ALTS record that a "
        "choice was made and never why, so the type would be unfillable. Resolved by decomposition "
        "rather than by a new type: the rationale is a causal argument position, which role.cause "
        "now provides on change_arrangement, relocate and undergo_transition. A separate decision "
        "type would still be unfillable, and would now be redundant as well",
        resolves="l2.decision_with_rationale",
        grounding=(
            _pb("decide.01", "decide", "ARG3 VSP subject-matter of decision"),
            _pb("choose.01", "choose, pick", "ARG2 DIR group or source"),
        ),
    ),
)


# The remaining thirty-nine new items. Grouped by what motivated them, because the motivation is
# shared: a role position PropBank declares, a band the persona corpus measures, or a structure
# schema.org types. None of them resolves a v1 deferral -- they are breadth v1 did not attempt.
_NEW_BREADTH: Final[tuple[CandidateDecision, ...]] = (
    _accept(
        "role.beneficiary",
        "l1:role.beneficiary",
        SourceKind.PROPBANK,
        "v1 recorded 'preference held on behalf of another person' as uncovered because role.holder "
        "assumes the speaker. PropBank declares a benefactive position separately from agent and "
        "recipient in exactly the frames memory uses: want.01 ARG2, choose.01 ARG3, reserve.01 "
        "ARG2, buy.01 ARG4",
        grounding=(_pb("want.01", "want, desire", "ARG2 GOL beneficiary"),),
    ),
    _accept(
        "role.comparison_target",
        "l1:role.comparison_target",
        SourceKind.PROPBANK,
        "prefer.01 declares ARG2 'entity compared to' where like.01 stops at ARG1, and favor.01 adds "
        "ARG3 'favored over'. v1's preference.comparative had no slot for the losing alternative, so "
        "a comparison's content was unrecoverable",
        grounding=(_pb("prefer.01", "to choose as more desirable", "ARG2 PPT entity compared to"),),
    ),
    _accept(
        "role.trigger",
        "l1:role.trigger",
        SourceKind.PROPBANK,
        "condition.01 declares ARG2 GOL 'dependent on'. v1 recorded conditional commitment as "
        "uncovered on the ground that SGD attests no conditional act -- true of the act labels, and "
        "false of the utterances: 472 condition on availability and 88 use an if/then frame",
        grounding=(
            _pb("condition.01", "to make dependent on a condition", "ARG2 GOL dependent on"),
        ),
    ),
    _accept(
        "qualifier.strength",
        "l1:qualifier.strength",
        SourceKind.MSC_PERSONAS,
        "v1 recorded preference strength as uncovered because intensifiers are unannotated and any "
        "scale would be an invented ordinal. The verb choice is the annotation: 2963 favourite, "
        "4102 love, 9517 like, 269 hate. schema.org's Rating with bestRating and worstRating is why "
        "this is a bounded ordinal rather than a number",
        grounding=(_so("schema:Rating", "an evaluation on a numeric scale, such as 1 to 5 stars"),),
    ),
    _accept(
        "qualifier.frequency",
        "l1:qualifier.frequency",
        SourceKind.MSC_PERSONAS,
        "v1 had one recurrence value and rested habit on 80 of 65245 sentences, calling it the "
        "weakest evidence in either layer. This build measures 295 explicit frequencies and 926 "
        "frequency adverbs, and schema.org separates repeatFrequency from repeatCount, which is "
        "what makes a rate distinguishable from a tally",
        grounding=(_so("schema:repeatFrequency", "defines the frequency at which Events occur"),),
    ),
    _accept(
        "strength.paramount",
        "l1:strength.paramount",
        SourceKind.MSC_PERSONAS,
        "2963 'my favourite' sentences, a superlative frame distinct from the love band because it "
        "excludes ties, which is why the item carries a uniqueness constraint",
        grounding=(
            _wn("n#07498210", "preference, penchant, predilection, taste: a strong liking"),
        ),
    ),
    _accept(
        "strength.strong",
        "l1:strength.strong",
        SourceKind.MSC_PERSONAS,
        "4102 love/adore and 269 hate/can't-stand sentences. love.01 and adore.01 are separate "
        "rolesets from like.01, so the intensity difference is lexicalized rather than adverbial",
        grounding=(_pb("love.01", "object of affection", "ARG1 PPT loved"),),
    ),
    _accept(
        "strength.moderate",
        "l1:strength.moderate",
        SourceKind.MSC_PERSONAS,
        "9517 like/enjoy sentences, the largest affect band and the reading when no intensifier is "
        "present, which makes it the default rather than a middle guess",
        grounding=(_pb("like.01", "have affection towards, be fond of, enjoy", "ARG1 PPT object"),),
    ),
    _accept(
        "strength.tolerant",
        "l1:strength.tolerant",
        SourceKind.PROPBANK,
        "the weakest band, and admitted on PropBank rather than on persona counts: tolerate.01 and "
        "mind.01 are distinct rolesets from like.01, so acceptance is its own attitude. The persona "
        "evidence is 6 sentences and would not have carried it; SGD's 472 'if available' and 14 'as "
        "long as' utterances are the attestation",
        grounding=(_pb("tolerate.01", "tolerate, put up with, the act of tolerating"),),
    ),
    _accept(
        "frequency.invariant",
        "l1:frequency.invariant",
        SourceKind.MSC_PERSONAS,
        "the always/never pole of the 926 frequency-adverb sentences, kept separate because a "
        "claim admitting no exception is falsified by one counterexample and a habitual claim is not",
    ),
    _accept(
        "frequency.habitual",
        "l1:frequency.habitual",
        SourceKind.MSC_PERSONAS,
        "295 explicit-frequency sentences plus the usually/often band. use.02 'accustomed to' takes "
        "ARG1 'custom', so habituality is lexicalized and not merely a count",
        grounding=(_pb("use.02", "accustomed to", "ARG1 PPT custom"),),
    ),
    _accept(
        "frequency.occasional",
        "l1:frequency.occasional",
        SourceKind.MSC_PERSONAS,
        "the sometimes/occasionally band, present because a minority-of-occasions claim predicts "
        "little and must not be read as a habit",
    ),
    _accept(
        "frequency.rare",
        "l1:frequency.rare",
        SourceKind.MSC_PERSONAS,
        "the rarely/never band. usual.01 declares ARG2 'entity arg1 is unusual for', so rarity is "
        "stated relative to a reference class rather than absolutely",
        grounding=(_pb("usual.01", "commonly occurring", "ARG2 GOL unusual for"),),
    ),
    _accept(
        "standing.contested",
        "l1:standing.contested",
        SourceKind.REPOSITORY_VOCABULARY,
        "domain.Lifecycle declares CONTRADICTED and UNCERTAIN and v1 carried neither, so an "
        "unresolved conflict had no atomic-layer standing and had to be represented as a "
        "supersession that had not happened",
    ),
)


# Coverage gaps that survive v2. Recorded rather than dropped: the register is what makes the
# no-masking rule checkable, and a shorter list obtained by lowering the bar would be worse than an
# honest one.
_UNCOVERED: Final[tuple[UncoveredExpression, ...]] = (
    UncoveredExpression(
        expression="a preference asserted on behalf of a third party whose own stance is unknown",
        observed_in=SourceKind.MSC_PERSONAS,
        why_not_covered=(
            "the atomic layer binds a preference to the holder who asserts it, and representing a "
            "reported preference requires a second holder slot the role inventory does not have"
        ),
        would_require="a reported-attitude role distinguishing asserter from holder",
    ),
    UncoveredExpression(
        expression="graded preference strength beyond a binary affinity",
        observed_in=SourceKind.MSC_PERSONAS,
        why_not_covered=(
            "the layer admits affinity, comparative and threshold, none of which carries an "
            "intensity scale, and inventing one would put a number where the corpora state a word"
        ),
        would_require="an intensity qualifier grounded in attested lexical gradation",
    ),
)


def _sources() -> tuple[SourceSnapshot, ...]:
    """The three published sources plus the corpora, each tied to bytes or counts.

    Counts are the ones parsed from the frozen snapshots. They exist so that "PropBank was
    consulted" is a checkable claim about specific bytes rather than a citation of PropBank in
    general.
    """
    return (
        SourceSnapshot(
            name="WordNet 3.0",
            consulted=True,
            locator="/public/home/wwb/datasets/ontology-sources/wordnet-3.0-nltk.zip",
            detail=(
                "used for sense disambiguation and lemma coverage on admitted items; synsets were "
                "not imported as types"
            ),
            observed_units=45,
            content_sha256=WORDNET_RAW_SHA256,
        ),
        SourceSnapshot(
            name="PropBank 3.4.0",
            consulted=True,
            locator="/public/home/wwb/datasets/ontology-sources/propbank-frames-3.4.0.tar.gz",
            detail=(
                "used to settle predicate senses and role sets, which is what v1 deferred "
                "role.cause and role.duration for; 11205 rolesets were read and a small number "
                "admitted"
            ),
            observed_units=11205,
            content_sha256=PROPBANK_RAW_SHA256,
        ),
        SourceSnapshot(
            name="schema.org 30.0",
            consulted=True,
            locator=(
                "/public/home/wwb/datasets/ontology-sources/"
                "schemaorg-30.0-current-https.jsonld"
            ),
            detail=(
                "used for type and property structure; the web-publishing vocabulary was left "
                "behind entirely"
            ),
            observed_units=1010,
            content_sha256=SCHEMAORG_RAW_SHA256,
        ),
        SourceSnapshot(
            name="Schema-Guided Dialogue (train)",
            consulted=True,
            locator="/public/home/wwb/datasets/SGD/train",
            detail="independent build corpus: slot and intent structure across 26 services",
            observed_units=16142,
        ),
        SourceSnapshot(
            name="Taskmaster-2",
            consulted=True,
            locator="/public/home/wwb/datasets/Taskmaster2",
            detail="independent build corpus: seven task domains, used for frame frequency only",
            observed_units=17304,
        ),
        SourceSnapshot(
            name="Multi-Session Chat personas",
            consulted=True,
            locator="/public/home/wwb/datasets/MSC/msc_personas_all.json",
            detail=(
                "independent build corpus: the only source attesting long-horizon personal "
                "statements, so it drives the preference and habit evidence"
            ),
            observed_units=65245,
        ),
    )


def build_decisions() -> DecisionLedger:
    """The ledger: every candidate decided, sorted, with the surviving gaps attached."""
    decisions = tuple(
        sorted(
            _NEW_ACCEPTED
            + _NEW_BREADTH
            + _decisions_from_items()
            + _carried_forward_refusals(),
            key=lambda d: d.candidate,
        )
    )
    return DecisionLedger(
        ontology_version=ONTOLOGY_VERSION,
        decisions=decisions,
        uncovered=_UNCOVERED,
    )


def build_provenance() -> ProvenanceSnapshot:
    """Provenance, including what was deliberately not imported.

    ``declined_imports`` is the part that matters. Without it the no-bulk-import rule cannot be
    checked: a reader has no way to tell restraint from never having looked.
    """
    return ProvenanceSnapshot(
        ontology_version=ONTOLOGY_VERSION,
        supersedes=SUPERSEDED_VERSION,
        sources=_sources(),
        discovery_split_use=(
            "the discovery split contributed general gap candidates only. No question, gold label, "
            "dataset identity or sample id was read, and no alias was derived from a benchmark item."
        ),
        judge_dependency="none; no judge call was made by this build",
        keol_role="offline construction and normalization only; no dynamic admission",
        declined_imports=(
            "PropBank: 11205 rolesets read, the overwhelming majority declined. Only senses that "
            "a person plausibly states about their own life were admitted; the newswire and "
            "financial frames that dominate the corpus were not.",
            "schema.org: 1010 classes and 1676 properties read, nearly all declined. The "
            "web-publishing vocabulary (CreativeWork, WebPage, Offer, breadcrumb) has no bearing "
            "on what a person remembers.",
            "WordNet: no synset was imported as a type. It was used to check that an admitted "
            "item's sense is the one the lemma actually carries.",
            "Domain verticals stay rejected as in v1: restaurant is Taskmaster-2's most frequent "
            "frame at 46133 occurrences and a foundation ontology containing it has fitted its "
            "build corpus.",
            "Speech acts stay rejected: an act is a property of an utterance rather than "
            "remembered content.",
            "Individuals and benchmark literals are excluded at the type level, so no named "
            "airline, date or order id appears.",
        ),
    )


def _decisions_from_items() -> tuple[CandidateDecision, ...]:
    """Derive a decision for every item not already decided explicitly.

    The explicit ledger above covers the candidates whose calls needed argument: the six v1
    deferrals the published sources settled, and the breadth additions. It does not cover every
    item, and the assembly validator rightly refuses an ontology containing items nobody decided
    on.

    Rather than author a reason per item after the fact, each decision is derived from the item's
    own recorded provenance. That keeps the ledger honest in a specific way: a decision cites the
    evidence that put the item in the layer, so it cannot claim grounds the item does not have. An
    item carrying no provenance at all would produce no decision and would then fail assembly,
    which is the correct outcome.
    """
    already = {d.candidate for d in _NEW_ACCEPTED + _NEW_BREADTH}
    derived: list[CandidateDecision] = []

    for freeze in (build_o_l1(), build_o_l2()):
        for entry in freeze.items:
            item = entry.item
            candidate = item.id.split(":", 1)[-1]
            if candidate in already:
                continue
            already.add(candidate)
            if not item.provenance:
                # Left undecided on purpose: assembly will reject it, which is better than
                # manufacturing grounds.
                continue
            first = item.provenance[0]
            derived.append(
                _accept(
                    candidate,
                    item.id,
                    first.source,
                    (
                        f"admitted on attested evidence: {first.evidence}"
                        if len(first.evidence) >= 20
                        else (
                            f"admitted on attested evidence from {first.source.value}: "
                            f"{first.evidence}"
                        )
                    ),
                )
            )
    return tuple(derived)


def _carried_forward_refusals() -> tuple[CandidateDecision, ...]:
    """v1's rejections and its still-unsettled deferrals, carried into v2's ledger.

    A ledger of 134 acceptances and no refusals would imply nothing was ever turned away, which is
    false and would quietly discard the most reusable part of v1's work: the reasoning behind 25
    rejections. Those grounds still hold in v2 — a domain vertical is no more admissible at 100
    items than at 67 — so they are carried with their original reasons rather than restated.

    A v1 deferral that v2 settled is not carried; the explicit acceptance above already names it.
    What remains deferred is carried as deferred, because a deferral silently dropped reads as a
    gap that was closed.
    """
    v1_path = (
        Path(__file__).resolve().parents[3] / "artifacts" / "ontology-v1" / "decisions.json"
    )
    if not v1_path.is_file():
        return ()

    document = cast("dict[str, Any]", json.loads(v1_path.read_text(encoding="utf-8")))
    entries: list[dict[str, Any]] = []
    for value in document.values():
        if isinstance(value, list):
            entries = cast("list[dict[str, Any]]", value)
            break
    settled = {
        d.resolves_v1_deferral
        for d in _NEW_ACCEPTED + _NEW_BREADTH
        if d.resolves_v1_deferral
    }

    carried: list[CandidateDecision] = []
    for entry in entries:
        disposition = str(entry.get("disposition", ""))
        candidate = str(entry.get("candidate", ""))
        reason = str(entry.get("reason", ""))
        if not candidate or len(reason) < 20:
            continue
        try:
            source = SourceKind(str(entry.get("source", "")))
        except ValueError:
            # A v1 source label with no v2 counterpart: attribute it to the carry-forward rather
            # than guessing a kind.
            source = SourceKind.ONTOLOGY_V1_CARRIED
        if disposition == "rejected":
            carried.append(_reject(candidate, source, reason))
        elif disposition == "deferred" and candidate not in settled:
            carried.append(
                _defer(
                    candidate,
                    source,
                    f"still deferred in v2: {reason}",
                )
            )
    return tuple(carried)
