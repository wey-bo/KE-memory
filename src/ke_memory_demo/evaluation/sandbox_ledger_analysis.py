"""The real ledger analysis, run inside the isolation sandbox.

This module is the analysis target handed to ``analyse_split_in_isolation``. Previously the
sandbox ran a probe while the committed ledger was computed in the parent process, which had the
whole corpus and all 500 gold labels loaded. Isolating a probe demonstrates that the sandbox
works; it does not isolate the analysis whose output is published.

So the pipeline, the classification and the counting all happen here, on a single split payload
delivered over stdin. There is no path back to the corpus: the namespace contains no split file,
no repository and no other split's gold.

The module is deliberately self-contained. It cannot import from ``ke_memory_demo``, because only
this file is staged into the sandbox — which is also what stops it reaching a sibling module that
might hold another split.
"""

from __future__ import annotations

import re
from typing import Any

# Shape labels only. Naming a module as the owner would claim attribution the fixture cannot
# support: the real extraction, mapping, ontology, query-compilation and retrieval layers do not
# run here, so an observation can describe what happened and not who caused it.
SHAPE_EMPTY_SELECTION = "empty_selection"
SHAPE_PARTIAL_OVERLAP = "partial_gold_overlap"
SHAPE_SUPERSET = "superset_selection"
SHAPE_DISJOINT = "disjoint_selection"
SHAPE_GOLD_OVER_LIMIT = "gold_delivery_over_limit"
SHAPE_UNRESOLVABLE_GOLD = "gold_handle_absent_from_corpus"
SHAPE_ANSWERED_WHEN_ABSTENTION_EXPECTED = "answered_when_gold_named_no_evidence"

# Which layers could produce each shape. Unordered and never reduced to a primary owner, because
# the fixture cannot separate them.
POSSIBLE_OWNERS: dict[str, tuple[str, ...]] = {
    SHAPE_EMPTY_SELECTION: (
        "extraction",
        "normalization",
        "ontology",
        "query_compiler",
        "retrieval",
    ),
    SHAPE_PARTIAL_OVERLAP: ("retrieval", "evidence_closure", "normalization"),
    SHAPE_SUPERSET: ("retrieval", "evidence_closure"),
    SHAPE_DISJOINT: ("normalization", "ontology", "query_compiler", "retrieval"),
    SHAPE_GOLD_OVER_LIMIT: ("delivery_budget",),
    SHAPE_UNRESOLVABLE_GOLD: ("extraction", "corpus_construction"),
    SHAPE_ANSWERED_WHEN_ABSTENTION_EXPECTED: (
        "abstention_policy",
        "retrieval",
        "query_compiler",
    ),
}

_WORD = re.compile(r"[a-z0-9]+")
_STOPWORDS = frozenset(
    {
        "the", "a", "an", "and", "or", "of", "to", "in", "on", "for", "with", "did", "do",
        "does", "is", "are", "was", "were", "what", "when", "where", "which", "who", "how",
        "why", "my", "i", "me", "you", "it", "that", "this", "about", "any", "have", "has",
        "had", "can", "could", "would", "there", "their", "before", "after",
    }
)

# The delivery budget for the retrieval arm. Selection has to fit what an arm delivers, not the
# whole model context: using the full-context number made the feasibility test vacuous.
DELIVERY_BUDGET_TOKENS = 24_576


def _terms(text: str) -> set[str]:
    return {t for t in _WORD.findall(text.lower()) if t not in _STOPWORDS and len(t) > 2}


def _approximate_tokens(length: int) -> int:
    return max(1, (length + 3) // 4)


def _select(question: str, turns: list[dict[str, Any]]) -> list[str]:
    """The lexical fixture selection, reproduced here so the sandbox is self-contained."""
    wanted = _terms(question)
    if not wanted:
        return [t["evidence_handle"] for t in turns[:10]]
    scored: list[tuple[int, int, str]] = []
    for index, turn in enumerate(turns):
        overlap = len(wanted & _terms(str(turn.get("text", ""))))
        if overlap:
            scored.append((overlap, -index, str(turn["evidence_handle"])))
    scored.sort(reverse=True)
    return [handle for _score, _order, handle in scored[:10]]


def analyse(payload: dict[str, Any]) -> dict[str, Any]:
    """Classify every question in one split, returning shapes and possible owners."""
    questions = payload["questions"]
    gold_by_id = {label["question_id"]: label for label in payload["gold"]}
    turns_by_conversation = payload["turns"]

    # Session membership travels in the payload: a turn does not name its session and opaque
    # handles share no prefix, so it cannot be reconstructed by string matching.
    session_members: dict[str, list[str]] = {
        str(session): [str(h) for h in handles]
        for session, handles in payload.get("session_members", {}).items()
    }

    observations: list[dict[str, Any]] = []
    shape_counts: dict[str, int] = {}
    owner_mentions: dict[str, int] = {}

    for question in questions:
        question_id = question["question_id"]
        label = gold_by_id.get(question_id)
        if label is None:
            continue
        turns = turns_by_conversation.get(question["conversation_handle"], [])
        handles = {str(t["evidence_handle"]) for t in turns}

        raw_refs = [str(r) for r in label.get("evidence_refs", []) if r]
        expanded: set[str] = set()
        unresolvable: list[str] = []
        for ref in raw_refs:
            if ref in handles:
                expanded.add(ref)
                continue
            members = [h for h in session_members.get(ref, []) if h in handles]
            if members:
                expanded.update(members)
            else:
                unresolvable.append(ref)

        selected = set(_select(str(question["question"]), turns))

        gold_turns = [t for t in turns if str(t["evidence_handle"]) in expanded]
        gold_tokens = sum(
            _approximate_tokens(len(str(t.get("text", "")))) for t in gold_turns
        )
        over_limit = bool(gold_turns) and gold_tokens > DELIVERY_BUDGET_TOKENS

        shape = _shape_for(
            expanded=expanded,
            selected=selected,
            unresolvable=bool(unresolvable),
            over_limit=over_limit,
        )
        if shape is None:
            continue

        owners = POSSIBLE_OWNERS[shape]
        observations.append(
            {
                "question_id": question_id,
                "shape": shape,
                "possible_owners": sorted(owners),
                "gold_handle_count": len(expanded),
                "selected_handle_count": len(selected),
                "overlap_count": len(expanded & selected),
                "gold_delivery_tokens": gold_tokens,
                "delivery_budget_tokens": DELIVERY_BUDGET_TOKENS,
            }
        )
        shape_counts[shape] = shape_counts.get(shape, 0) + 1
        for owner in owners:
            owner_mentions[owner] = owner_mentions.get(owner, 0) + 1

    total = len(observations)
    return {
        "split": payload["split"],
        "questions_analysed": len(questions),
        "observation_count": total,
        "shape_counts": dict(sorted(shape_counts.items())),
        "possible_owner_mentions": dict(sorted(owner_mentions.items())),
        "possible_owner_share": {
            owner: count / total for owner, count in sorted(owner_mentions.items())
        }
        if total
        else {},
        "observations": observations,
        "what_this_is": (
            "shape inventory produced inside the isolation sandbox from one split payload. Shapes "
            "describe what happened; possible_owners is unordered and no primary owner is chosen, "
            "because the real extraction, mapping, ontology, query-compilation and retrieval "
            "layers did not run"
        ),
        "gold_labels_visible": len(gold_by_id),
    }


def _shape_for(
    *,
    expanded: set[str],
    selected: set[str],
    unresolvable: bool,
    over_limit: bool,
) -> str | None:
    if expanded == selected and not unresolvable:
        return None
    if unresolvable:
        return SHAPE_UNRESOLVABLE_GOLD
    if over_limit:
        return SHAPE_GOLD_OVER_LIMIT
    if not expanded and selected:
        return SHAPE_ANSWERED_WHEN_ABSTENTION_EXPECTED
    if expanded and not selected:
        return SHAPE_EMPTY_SELECTION
    if expanded < selected:
        return SHAPE_SUPERSET
    if expanded & selected:
        return SHAPE_PARTIAL_OVERLAP
    return SHAPE_DISJOINT
