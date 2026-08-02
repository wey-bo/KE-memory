"""Corpus-driven discovery: build a frozen corpus and classify what goes wrong.

Runs from the frozen harness commit. The corpus is built once, inside the sandbox, from
conversations only; questions and gold are loaded in this controller process after the
sandboxed build has exited.

The point of the issue ledger is to resist a single attractive explanation. Attributing every
failure to ontology insufficiency would produce a large ontology and no diagnosis, so each
observation is classified into one of eight classes, and a class is only assigned when its own
evidence is present. Where the evidence does not distinguish between two classes, the
observation is recorded as ambiguous rather than assigned to the more convenient one.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from .channels import BenchmarkQuestion, GoldLabels, PublicTurn

NonEmptyString = Annotated[str, Field(min_length=1)]


class IssueClass(StrEnum):
    """The eight failure classes, kept distinct so attribution stays honest."""

    EXTRACTION_STRUCTURAL = "extraction_structural"
    NORMALIZATION_GAP = "normalization_gap"
    ONTOLOGY_GAP = "ontology_gap"
    QUERY_COMPILER = "query_compiler"
    RETRIEVAL_RANKING = "retrieval_ranking"
    EVIDENCE_CLOSURE = "evidence_closure"
    SEMANTIC_HANDLING = "semantic_handling"
    CONTEXT_COVERAGE = "context_coverage"


# What must be observable before a class may be assigned. Recorded in the artifact so a
# reader can check the reasoning rather than trusting the label.
CLASS_EVIDENCE_REQUIREMENT: dict[IssueClass, str] = {
    IssueClass.EXTRACTION_STRUCTURAL: (
        "a surface unit is missing, malformed, or split or merged wrongly, independent of any "
        "ontology decision"
    ),
    IssueClass.NORMALIZATION_GAP: (
        "the same entity, role or predicate appears under variant surface forms that were not "
        "unified, while the target concept itself exists"
    ),
    IssueClass.ONTOLOGY_GAP: (
        "no existing type, relation or operator can express the fact, so normalization could "
        "not have fixed it"
    ),
    IssueClass.QUERY_COMPILER: (
        "the question compiled to a plan that does not express what was asked, or was declared "
        "unsupported while the memory holds the answer"
    ),
    IssueClass.RETRIEVAL_RANKING: (
        "the gold evidence is present and expressible, and the plan is right, but the evidence "
        "was not selected or was ranked below the cut"
    ),
    IssueClass.EVIDENCE_CLOSURE: (
        "the selected evidence is individually correct but does not close: a derivation or "
        "supporting span is missing"
    ),
    IssueClass.SEMANTIC_HANDLING: (
        "abstention, time, modality, negation, conflict or supersession was handled wrongly, "
        "with the relevant evidence present"
    ),
    IssueClass.CONTEXT_COVERAGE: (
        "the conversation or evidence exceeded a frozen budget, so no selection could have "
        "succeeded"
    ),
}


class _Record(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class Observation(_Record):
    """One classified failure, with the evidence that justifies its class."""

    question_id: NonEmptyString
    issue_class: IssueClass
    evidence: NonEmptyString
    gold_evidence_count: int
    selected_evidence_count: int
    ambiguous_with: tuple[IssueClass, ...] = ()
    ontology_candidate_hint: str = ""

    @property
    def is_ambiguous(self) -> bool:
        return bool(self.ambiguous_with)


class IssueLedger(_Record):
    """The audit surface for discovery."""

    corpus_id: NonEmptyString
    split: NonEmptyString
    observations: tuple[Observation, ...]

    def counts(self) -> dict[str, int]:
        counts = {str(cls): 0 for cls in IssueClass}
        for observation in self.observations:
            counts[str(observation.issue_class)] += 1
        return counts

    def ambiguous_count(self) -> int:
        return sum(1 for o in self.observations if o.is_ambiguous)

    def ontology_share(self) -> float:
        """Fraction attributed to a genuine ontology gap.

        Reported prominently because a high share is a warning sign about the classification,
        not a finding about the ontology.
        """
        if not self.observations:
            return 0.0
        gaps = sum(
            1 for o in self.observations if o.issue_class is IssueClass.ONTOLOGY_GAP
        )
        return gaps / len(self.observations)


def classify(
    question: BenchmarkQuestion,
    label: GoldLabels,
    available: Sequence[PublicTurn],
    selected_handles: Sequence[str],
    *,
    context_limited: bool,
    plan_terms: Sequence[str],
    session_members: Mapping[str, Sequence[str]] | None = None,
) -> Observation | None:
    """Classify one question's outcome, or return None when nothing went wrong.

    Deliberately conservative. Where the available signals cannot separate two classes, both
    are recorded and the observation is marked ambiguous, because a confident wrong label is
    worse than an acknowledged uncertainty.
    """
    gold = {ref for ref in label.evidence_refs if ref}
    expanded = _expand(gold, available, session_members or {})
    got = set(selected_handles)

    if expanded == got:
        return None

    handles = {t.evidence_handle for t in available}
    counts = (len(expanded), len(got))

    if context_limited:
        return Observation(
            question_id=question.question_id,
            issue_class=IssueClass.CONTEXT_COVERAGE,
            evidence=(
                "the conversation exceeded the frozen budget, so no selection could have "
                "recovered the gold set"
            ),
            gold_evidence_count=counts[0],
            selected_evidence_count=counts[1],
        )

    # A gold reference is unresolvable only when it names neither a turn handle nor a session
    # with members present. Subtracting turn handles from session references, as an earlier
    # version did, marks every correctly resolved session reference as missing and reports
    # almost the whole corpus as an extraction failure.
    unresolvable = {
        ref
        for ref in gold
        if ref not in handles and not _members_present(ref, session_members or {}, handles)
    }
    if unresolvable:
        return Observation(
            question_id=question.question_id,
            issue_class=IssueClass.EXTRACTION_STRUCTURAL,
            evidence=(
                f"gold names {len(unresolvable)} handle(s) absent from the built corpus, so "
                "extraction never produced the unit"
            ),
            gold_evidence_count=counts[0],
            selected_evidence_count=counts[1],
        )

    if not expanded and got:
        return Observation(
            question_id=question.question_id,
            issue_class=IssueClass.SEMANTIC_HANDLING,
            evidence=(
                "gold names no evidence, so abstention was required, but evidence was selected"
            ),
            gold_evidence_count=counts[0],
            selected_evidence_count=counts[1],
        )

    if expanded and not got:
        # Nothing selected at all. Either the plan expressed nothing usable, or the ontology
        # cannot express the question. The two are not separable from selection output alone.
        return Observation(
            question_id=question.question_id,
            issue_class=IssueClass.QUERY_COMPILER,
            evidence=(
                f"the plan produced {len(plan_terms)} term(s) and selected nothing while "
                f"{len(expanded)} gold unit(s) were available and expressible"
            ),
            gold_evidence_count=counts[0],
            selected_evidence_count=counts[1],
            ambiguous_with=(IssueClass.ONTOLOGY_GAP,),
            ontology_candidate_hint=(
                "check whether any existing type or relation can express this question before "
                "proposing a new one"
            ),
        )

    if expanded <= got:
        return Observation(
            question_id=question.question_id,
            issue_class=IssueClass.RETRIEVAL_RANKING,
            evidence=(
                f"every gold unit was selected alongside {len(got - expanded)} extra unit(s), "
                "so recall held and precision failed"
            ),
            gold_evidence_count=counts[0],
            selected_evidence_count=counts[1],
        )

    if got & expanded:
        return Observation(
            question_id=question.question_id,
            issue_class=IssueClass.EVIDENCE_CLOSURE,
            evidence=(
                f"{len(got & expanded)} of {len(expanded)} gold unit(s) were selected, so the "
                "evidence set does not close"
            ),
            gold_evidence_count=counts[0],
            selected_evidence_count=counts[1],
            ambiguous_with=(IssueClass.RETRIEVAL_RANKING,),
        )

    return Observation(
        question_id=question.question_id,
        issue_class=IssueClass.RETRIEVAL_RANKING,
        evidence=(
            "the selection and the gold set are disjoint while the gold units were available"
        ),
        gold_evidence_count=counts[0],
        selected_evidence_count=counts[1],
        ambiguous_with=(IssueClass.NORMALIZATION_GAP, IssueClass.QUERY_COMPILER),
        ontology_candidate_hint=(
            "a disjoint selection often indicates surface-form variance rather than a missing "
            "concept; rule normalization out first"
        ),
    )


def _members_present(
    ref: str,
    session_members: Mapping[str, Sequence[str]],
    handles: set[str],
) -> bool:
    return any(handle in handles for handle in session_members.get(ref, ()))


def _expand(
    refs: set[str],
    available: Sequence[PublicTurn],
    session_members: Mapping[str, Sequence[str]],
) -> set[str]:
    """Resolve a gold reference to turn handles.

    LongMemEval gold names sessions while selection is scored per turn. Opaque handles share
    no prefix, so membership comes from the loader rather than from string matching; relying on
    a prefix silently resolved every session reference to nothing.
    """
    handles = {t.evidence_handle for t in available}
    expanded: set[str] = set()
    for ref in refs:
        if ref in handles:
            expanded.add(ref)
            continue
        expanded.update(h for h in session_members.get(ref, ()) if h in handles)
    return expanded
