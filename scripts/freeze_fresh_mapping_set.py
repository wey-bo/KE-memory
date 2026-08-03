"""Freeze the fresh mapping set for mapper v3, before any mapper v3 code exists.

Ordering is the guarantee. This runs while ``mapper_v3`` does not exist, so the set cannot have shaped
the frames, the thresholds or the evidence types. A set frozen afterwards proves nothing, because any
choice could have been made with these expressions in view.

Three disjointness requirements, all enforced by exact text rather than by split membership:

- disjoint from the **discovery** split, which mapper development may read
- disjoint from the **spent 120-expression sample**, which is now exposed regression only
- disjoint from the **validation** split used for that spent sample

The pool is therefore LongMemEval's held_out split, which no earlier stage has touched, plus LoCoMo.
Drawing from two corpora means a mapper tuned to one register cannot look competent by accident.

The spent sample stays available as regression: its 120 expressions were where the four O_v3 families
were found, so any conclusion drawn from them is contaminated, but a regression check against them
remains legitimate.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, cast

from ke_memory_demo.core.json import canonical_json
from ke_memory_demo.evaluation.benchmark_loaders import load_locomo, load_longmemeval
from ke_memory_demo.evaluation.data_boundaries import Split, plan_splits

LONGMEMEVAL = Path("/public/home/wwb/datasets/LongMemEval/longmemeval_oracle.json")
LOCOMO = Path("/public/home/wwb/datasets/LoCoMo/locomo10.json")
SPENT_SAMPLE = Path("artifacts/mapper-v2-validation/natural-expression-sample.json")
OUTPUT_DIR = Path("artifacts/mapper-v3-validation")

# Fixed before the draw, and different from the spent sample's salt so the two draws cannot coincide.
SAMPLE_SALT = "fresh-mapping-set-v3"
TARGET_SIZE = 160

MINIMUM_CHARS = 25
MAXIMUM_CHARS = 400


def _rank(text: str) -> str:
    return hashlib.sha256(f"{SAMPLE_SALT}:{text}".encode()).hexdigest()


def _eligible(
    source_id: str,
    turns: list[tuple[str, str]],
    excluded_text: set[str],
) -> list[dict[str, str]]:
    """Length-filtered, deduplicated, deterministically ranked candidates.

    Filtering is by length only. Selecting on whether the ontology covers a turn would bias the set
    toward what O_v3 already knows and flatter the coverage measurement it exists to produce.
    """
    seen: set[str] = set()
    out: list[dict[str, str]] = []
    for speaker, text in turns:
        stripped = text.strip()
        if not (MINIMUM_CHARS <= len(stripped) <= MAXIMUM_CHARS):
            continue
        if stripped in excluded_text:
            continue
        digest = hashlib.sha256(stripped.encode()).hexdigest()
        if digest in seen:
            continue
        seen.add(digest)
        out.append(
            {
                "source_pool": source_id,
                "speaker": speaker,
                "text": stripped,
                "rank_key": _rank(stripped),
            }
        )
    out.sort(key=lambda entry: entry["rank_key"])
    return out


def main() -> int:
    # Everything the mapper line may read, plus the spent sample, must be excluded by exact text.
    longmemeval = load_longmemeval(LONGMEMEVAL)
    plan = plan_splits("lme", [q.question_id for q in longmemeval.questions.questions])

    def _text_for(split: Split) -> set[str]:
        handles = {
            q.conversation_handle
            for q in longmemeval.questions.questions
            if q.question_id in set(plan.ids_for(split))
        }
        return {
            turn.text.strip()
            for conversation in longmemeval.build_input.conversations
            if conversation.conversation_handle in handles
            for session in conversation.sessions
            for turn in session.turns
        }

    discovery_text = _text_for(Split.DISCOVERY)
    validation_text = _text_for(Split.VALIDATION)
    spent = cast("dict[str, Any]", json.loads(SPENT_SAMPLE.read_text(encoding="utf-8")))
    spent_text = {
        str(cast("dict[str, Any]", e)["text"]).strip()
        for e in cast("list[Any]", spent["expressions"])
    }
    excluded = discovery_text | validation_text | spent_text

    held_out_handles = {
        q.conversation_handle
        for q in longmemeval.questions.questions
        if q.question_id in set(plan.ids_for(Split.HELD_OUT))
    }
    lme_turns = [
        (turn.speaker, turn.text)
        for conversation in longmemeval.build_input.conversations
        if conversation.conversation_handle in held_out_handles
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

    pools = {
        "longmemeval_held_out": _eligible("lme_held_out", lme_turns, excluded),
        "locomo_remaining": _eligible("locomo", locomo_turns, excluded),
    }

    per_pool = TARGET_SIZE // 2
    drawn: list[dict[str, str]] = []
    for pool in pools.values():
        drawn.extend(pool[:per_pool])
    drawn.sort(key=lambda entry: entry["rank_key"])

    expressions = [
        {
            "expression_id": f"fx-{index:06d}",
            "speaker": entry["speaker"],
            "text": entry["text"],
            "source_pool": entry["source_pool"],
        }
        for index, entry in enumerate(drawn)
    ]

    # Contamination check, run rather than asserted.
    drawn_text = {e["text"] for e in expressions}
    overlaps = {
        "discovery": len(drawn_text & discovery_text),
        "validation": len(drawn_text & validation_text),
        "spent_sample": len(drawn_text & spent_text),
    }
    if any(overlaps.values()):
        print(f"FAIL: the fresh set overlaps earlier data: {overlaps}")
        return 1

    payload: dict[str, Any] = {
        "artifact": "fresh mapping set for mapper v3",
        "standing": "frozen_before_mapper_v3_exists",
        "why_frozen_first": (
            "mapper v3 does not exist yet, so this set cannot have shaped its frames, thresholds or "
            "evidence types. A set frozen afterwards could not rule that out."
        ),
        "salt": SAMPLE_SALT,
        "salt_differs_from_spent_sample": True,
        "pools": {
            "longmemeval_held_out": (
                "the held_out split, untouched by discovery, by the validation split and by the spent "
                "sample"
            ),
            "locomo_remaining": "LoCoMo turns not drawn into the spent sample",
        },
        "pool_sizes": {name: len(pool) for name, pool in pools.items()},
        "disjointness": {
            "enforced_by": "exact text, not split membership alone",
            "excluded_pools": [
                "discovery split (readable by mapper development)",
                "validation split (used for the spent sample)",
                "the spent 120-expression sample",
            ],
            "measured_overlaps": overlaps,
            "why_exact_text": (
                "an utterance can recur verbatim across conversations, so id-based splitting leaked "
                "seven overlaps when the previous sample was drawn"
            ),
        },
        "eligibility": {
            "minimum_chars": MINIMUM_CHARS,
            "maximum_chars": MAXIMUM_CHARS,
            "rule": (
                "length only. Selecting on whether O_v3 covers a turn would bias the set toward what "
                "the ontology already knows and flatter the coverage measurement."
            ),
        },
        "sample_size": len(expressions),
        "id_rule": "opaque ids; no dataset, conversation or question identity",
        "expressions": expressions,
        "spent_sample_status": (
            "the earlier 120 expressions remain available as exposed regression. The four O_v3 "
            "families were identified from them, so any conclusion drawn from them is contaminated, "
            "but a regression check against them is legitimate."
        ),
        "annotation_required_before_use": (
            "this set carries no labels. It must be annotated by a line that cannot see mapper v3, "
            "exactly as the previous set was."
        ),
        "judge": "not called",
    }
    payload["set_sha256"] = hashlib.sha256(
        canonical_json({"salt": SAMPLE_SALT, "expressions": expressions})
    ).hexdigest()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUTPUT_DIR / "fresh-mapping-set.json").write_text(
        json.dumps(payload, indent=1, sort_keys=True), encoding="utf-8"
    )

    print(f"fresh set size: {payload['sample_size']}")
    for name, size in payload["pool_sizes"].items():
        print(f"  pool {name}: {size} eligible")
    print(f"overlaps with earlier data: {overlaps}")
    print(f"set sha256: {payload['set_sha256']}")
    print(f"standing: {payload['standing']}")
    print(f"artifact: {OUTPUT_DIR / 'fresh-mapping-set.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
