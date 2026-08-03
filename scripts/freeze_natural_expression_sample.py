"""Freeze the natural-expression validation sample, before mapper v2 exists.

Order is the point. The expressions are drawn and hashed now, while mapper v2 has not been built, so
the sample cannot have driven the mapper's design. A sample frozen afterwards proves nothing: any
threshold could have been chosen with these very expressions in view.

Sampling is from real conversation turns. Nothing is composed by reading an ontology item, which is
what made the retired 18-case probe a probe rather than a measurement.

Ids are opaque. A mapper receiving ``expr-000123`` cannot special-case a dataset; one receiving
``LONGMEMEVAL-abc`` can.

Two sources, deliberately: LongMemEval's validation split (its discovery split is what the mapper
line may use, so validation is disjoint from mapper development) and LoCoMo, which has never been
used for discovery at all. Drawing from both means a mapper tuned to one corpus's register cannot
look competent on the sample by accident.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from ke_memory_demo.core.json import canonical_json
from ke_memory_demo.evaluation.benchmark_loaders import load_locomo, load_longmemeval
from ke_memory_demo.evaluation.data_boundaries import Split, plan_splits

LONGMEMEVAL = Path("/public/home/wwb/datasets/LongMemEval/longmemeval_oracle.json")
LOCOMO = Path("/public/home/wwb/datasets/LoCoMo/locomo10.json")
OUTPUT_DIR = Path("artifacts/mapper-v2-validation")

# Fixed before drawing. Recorded in the artifact so the draw is reproducible and cannot be re-rolled
# until it looks convenient.
SAMPLE_SALT = "natural-expression-validation-v1"
TARGET_SIZE = 120

# Turns shorter than this carry no propositional content to map. Excluded by length rather than by
# inspecting whether the ontology happens to cover them, which would bias the sample toward what the
# ontology already knows.
MINIMUM_CHARS = 25
MAXIMUM_CHARS = 400


def _rank(salt: str, text: str) -> str:
    return hashlib.sha256(f"{salt}:{text}".encode()).hexdigest()


def _eligible_turns(source_id: str, turns: list[tuple[str, str]]) -> list[dict[str, str]]:
    """Filter to turns long enough to carry a proposition, then rank deterministically."""
    seen: set[str] = set()
    eligible: list[dict[str, str]] = []
    for speaker, text in turns:
        stripped = text.strip()
        if not (MINIMUM_CHARS <= len(stripped) <= MAXIMUM_CHARS):
            continue
        # Exact duplicates would let one utterance carry several sample slots.
        digest = hashlib.sha256(stripped.encode()).hexdigest()
        if digest in seen:
            continue
        seen.add(digest)
        eligible.append(
            {
                "source_id": source_id,
                "speaker": speaker,
                "text": stripped,
                "rank_key": _rank(SAMPLE_SALT, stripped),
            }
        )
    eligible.sort(key=lambda entry: entry["rank_key"])
    return eligible


def main() -> int:
    longmemeval = load_longmemeval(LONGMEMEVAL)
    plan = plan_splits(
        "lme", [q.question_id for q in longmemeval.questions.questions]
    )
    validation_ids = set(plan.ids_for(Split.VALIDATION))
    validation_handles = {
        q.conversation_handle
        for q in longmemeval.questions.questions
        if q.question_id in validation_ids
    }
    lme_turns = [
        (turn.speaker, turn.text)
        for conversation in longmemeval.build_input.conversations
        if conversation.conversation_handle in validation_handles
        for session in conversation.sessions
        for turn in session.turns
    ]

    locomo = load_locomo(LOCOMO)
    locomo_turns = [
        (turn.speaker, turn.text)
        for conversation in locomo.build_input.conversations
        for session in conversation.sessions
        for turn in session.turns
    ]

    # Text the mapper line may see must not reach the validation sample. Splitting by question id
    # is not sufficient: an utterance can recur verbatim across conversations, and seven such turns
    # did overlap on the first draw. Isolation is by exact text, not by split membership alone.
    discovery_ids = set(plan.ids_for(Split.DISCOVERY))
    discovery_handles = {
        q.conversation_handle
        for q in longmemeval.questions.questions
        if q.question_id in discovery_ids
    }
    discovery_text = {
        turn.text.strip()
        for conversation in longmemeval.build_input.conversations
        if conversation.conversation_handle in discovery_handles
        for session in conversation.sessions
        for turn in session.turns
    }

    def _excluding_discovery(
        source_id: str, turns: list[tuple[str, str]]
    ) -> list[dict[str, str]]:
        return [
            entry
            for entry in _eligible_turns(source_id, turns)
            if entry["text"] not in discovery_text
        ]

    pools = {
        "longmemeval_validation_split": _excluding_discovery("lme_validation", lme_turns),
        "locomo_never_used_for_discovery": _excluding_discovery("locomo", locomo_turns),
    }

    # Half from each pool, so neither corpus's register dominates.
    per_pool = TARGET_SIZE // 2
    drawn: list[dict[str, str]] = []
    for pool in pools.values():
        drawn.extend(pool[:per_pool])
    drawn.sort(key=lambda entry: entry["rank_key"])

    expressions: list[dict[str, Any]] = []
    for index, entry in enumerate(drawn):
        expressions.append(
            {
                # Opaque: no dataset name, no conversation id, no question id.
                "expression_id": f"expr-{index:06d}",
                "speaker": entry["speaker"],
                "text": entry["text"],
                "source_pool": entry["source_id"],
            }
        )

    sample: dict[str, Any] = {
        "artifact": "natural-expression validation sample",
        "standing": "frozen_before_mapper_v2_exists",
        "sampling_rule": (
            "drawn from real conversation turns and ranked by sha256(salt + text), so the draw is "
            "reproducible and independent of file order. No expression was composed by reading an "
            "ontology item."
        ),
        "why_frozen_first": (
            "mapper v2 has not been built. A sample frozen afterwards could not rule out that its "
            "thresholds were chosen with these expressions in view."
        ),
        "salt": SAMPLE_SALT,
        "pools": {
            "longmemeval_validation_split": (
                "disjoint from the discovery split the mapper line may use"
            ),
            "locomo_never_used_for_discovery": (
                "never used for discovery at all, so it cannot reward corpus-specific tuning"
            ),
        },
        "eligibility": {
            "minimum_chars": MINIMUM_CHARS,
            "maximum_chars": MAXIMUM_CHARS,
            "rule": (
                "filtered by length only. Filtering by whether the ontology covers a turn would bias "
                "the sample toward what the ontology already knows and would flatter the ceiling "
                "measurement."
            ),
            "exact_duplicates_removed": True,
            "discovery_text_excluded": (
                "any turn whose exact text appears anywhere in the mapper line's discovery split is "
                "removed. Splitting by question id alone left seven verbatim overlaps on the first "
                "draw, because an utterance can recur across conversations."
            ),
        },
        "pool_sizes": {name: len(pool) for name, pool in pools.items()},
        "sample_size": len(expressions),
        "id_rule": "opaque expression ids; no dataset, conversation or question identity",
        "expressions": expressions,
        "annotation_line_may_see": [
            "these expressions",
            "ontology v2 (O_L1, O_L2, M_L1_to_L2)",
        ],
        "mapper_line_may_not_see": [
            "these expressions",
            "any label produced from them",
        ],
        "judge": "not called",
    }
    sample["sample_sha256"] = hashlib.sha256(
        canonical_json(
            {"salt": SAMPLE_SALT, "expressions": expressions}
        )
    ).hexdigest()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUTPUT_DIR / "natural-expression-sample.json").write_text(
        json.dumps(sample, indent=1, sort_keys=True), encoding="utf-8"
    )

    print(f"sample size: {sample['sample_size']}")
    for name, size in sample["pool_sizes"].items():
        print(f"  pool {name}: {size} eligible")
    print(f"sample sha256: {sample['sample_sha256']}")
    print(f"frozen before mapper v2 exists: {sample['standing']}")
    print(f"artifact: {OUTPUT_DIR / 'natural-expression-sample.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
