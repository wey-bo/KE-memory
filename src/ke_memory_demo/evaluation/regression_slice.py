"""Regression-slice loader onto the three-channel split.

The 32-item slice is the only input Stage 2 is allowed to use. It spans four files, and
the separation between them is what makes the anti-cheating contract expressible:

- ``slice.json`` holds ``public_items``: the real natural questions.
- ``evidence-corpus.json`` holds candidate evidence per item, addressed by ``unit_id``.
- ``gold.json`` and ``gold-evidence.json`` hold answers, rubrics and the correct subset.

Three defects here were caught in review and are worth naming, because each produced
plausible-looking output while being wrong: the loader used each item's ``source_ref``
pointer as the question text, so no arm ever saw a real question; it addressed evidence by
loop index while gold addressed it by ``unit_id``, driving every evidence metric to zero;
and it put ``gold_sha256`` into public source identity.

Freeze evidence lives in :mod:`ke_memory_demo.evaluation.freeze_receipt`.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

from .channels import (
    BenchmarkId,
    HandleMint,
    BenchmarkQuestion,
    ChannelError,
    GoldChannel,
    GoldLabels,
    LoadedBenchmark,
    MemoryBuildInput,
    PublicConversation,
    PublicSession,
    PublicTurn,
    QuestionChannel,
)

SLICE_ITEM_COUNT = 32


class RegressionSliceError(ChannelError):
    """The regression slice is missing, malformed, or not the expected 32 items."""


def load_regression_slice(slice_dir: Path) -> LoadedBenchmark:
    """Load the slice with public content, questions and gold strictly separated."""
    public_payload = _read_json(slice_dir / "slice.json")
    gold_payload = _read_json(slice_dir / "gold.json")
    corpus_payload = _read_json(slice_dir / "evidence-corpus.json")
    gold_evidence_payload = _read_json(slice_dir / "gold-evidence.json")

    gold_doc = cast(dict[str, Any], gold_payload)
    items = [cast(dict[str, Any], i) for i in cast(list[Any], gold_doc.get("items") or [])]
    if len(items) != SLICE_ITEM_COUNT:
        raise RegressionSliceError(
            f"regression slice must contain exactly {SLICE_ITEM_COUNT} items, found {len(items)}"
        )

    public_items = {
        str(cast(dict[str, Any], item).get("item_id")): cast(dict[str, Any], item)
        for item in cast(
            list[Any], cast(dict[str, Any], public_payload).get("public_items") or []
        )
    }
    if len(public_items) != SLICE_ITEM_COUNT:
        raise RegressionSliceError(
            f"slice.json must carry exactly {SLICE_ITEM_COUNT} public items, "
            f"found {len(public_items)}"
        )

    corpus = cast(dict[str, Any], cast(dict[str, Any], corpus_payload).get("items") or {})
    gold_evidence = cast(
        dict[str, Any], cast(dict[str, Any], gold_evidence_payload).get("items") or {}
    )

    conversations: list[PublicConversation] = []
    questions: list[BenchmarkQuestion] = []
    labels: list[GoldLabels] = []
    # Handles must not disclose the benchmark, conversation or question category, all of
    # which "slice-BEAM-100K-C001-abstention-001" states outright.
    mint = HandleMint()

    for item in items:
        item_id = str(item.get("item_id") or "")
        if not item_id:
            raise RegressionSliceError("regression slice item is missing item_id")

        candidates = [
            cast(dict[str, Any], e) for e in cast(list[Any], corpus.get(item_id) or [])
        ]
        handle = mint.mint("conversation", f"slice-{item_id}")
        turns: list[PublicTurn] = []
        for index, candidate in enumerate(candidates):
            text = str(candidate.get("text") or "")
            if not text.strip():
                continue
            # Both the corpus and the gold file address evidence by unit_id. Using the
            # loop index instead invents an id space gold cannot match.
            unit_id = mint.mint("turn", f"{item_id}::{candidate.get('unit_id') or index}")
            metadata = cast(dict[str, Any], candidate.get("metadata") or {})
            turns.append(
                PublicTurn(
                    evidence_handle=unit_id,
                    speaker=str(metadata.get("role") or "unknown"),
                    text=text,
                    approximate_tokens=max(1, (len(text) + 3) // 4),
                )
            )

        if turns:
            conversations.append(
                PublicConversation(
                    conversation_handle=handle,
                    sessions=(
                        PublicSession(
                            session_handle=mint.mint("session", f"{item_id}::s0"),
                            turns=tuple(turns),
                            metadata={"public_session_ordinal": 0},
                        ),
                    ),
                )
            )

        public_item = public_items.get(item_id)
        if public_item is None:
            raise RegressionSliceError(f"slice.json has no public item for {item_id}")
        question_text = str(public_item.get("question") or "").strip()
        if not question_text:
            raise RegressionSliceError(f"slice.json public item {item_id} has no question")

        questions.append(
            BenchmarkQuestion(
                question_id=item_id,
                conversation_handle=handle,
                question=question_text,
            )
        )

        metadata = cast(dict[str, Any], item.get("metadata") or {})
        rubric = [str(r) for r in cast(list[Any], metadata.get("rubric") or ())]
        policy = str(item.get("answer_policy") or "")
        labels.append(
            GoldLabels(
                question_id=item_id,
                conversation_handle=handle,
                answer=str(item.get("answer", "")),
                category=str(item.get("category", "")),
                evidence_refs=tuple(
                    opaque
                    for ref in _gold_evidence_ids(gold_evidence.get(item_id))
                    if (opaque := mint.opaque_for(f"{item_id}::{ref}")) is not None
                ),
                rubrics=tuple(rubric),
                answer_policy=policy,
                requires_manual_review=policy == "manual_required",
                metadata={
                    "slice_group": str(item.get("slice_group", "")),
                    "origin_benchmark": str(item.get("benchmark", "")),
                    "candidate_evidence_count": len(candidates),
                },
            )
        )

    if not conversations:
        raise RegressionSliceError("regression slice produced no public conversations")

    build_input = MemoryBuildInput(
        conversations=tuple(conversations),
        # Only allowlisted keys. gold_sha256 previously lived here, which put a gold
        # fingerprint into the channel a memory build reads.

    )
    return LoadedBenchmark(
        benchmark=BenchmarkId.REGRESSION_SLICE,
        build_input=build_input,
        questions=QuestionChannel(
            benchmark=BenchmarkId.REGRESSION_SLICE, questions=tuple(questions)
        ),
        gold=GoldChannel(benchmark=BenchmarkId.REGRESSION_SLICE, labels=tuple(labels)),
        # Controller-side only: bound to the freeze receipt after the build finishes.
        source_identity={
            "loader_id": "regression-slice-loader",
            "loader_version": "3",
            "handle_mapping_size": len(mint.mapping),
        },
    )


def slice_item_ids(loaded: LoadedBenchmark) -> tuple[str, ...]:
    """Item ids a fresh sample must exclude to avoid contamination."""
    return tuple(sorted(label.question_id for label in loaded.gold.labels))


def _gold_evidence_ids(entries: object) -> tuple[str, ...]:
    """Extract evidence handles from gold entries.

    ``gold-evidence.json`` stores full evidence records, not bare ids. Coercing each with
    ``str()`` produces a stringified dict that can never match a unit id, so ``unit_id`` is
    read explicitly while a plain string is still accepted.
    """
    if not isinstance(entries, list):
        return ()
    ids: list[str] = []
    for entry in cast(list[Any], entries):
        if isinstance(entry, dict):
            typed = cast(dict[str, Any], entry)
            handle = typed.get("unit_id") or typed.get("source_ref")
            if handle is not None:
                ids.append(str(handle))
        elif entry is not None:
            ids.append(str(entry))
    return tuple(ids)


def _read_json(path: Path) -> object:
    try:
        with path.open("r", encoding="utf-8") as stream:
            return json.load(stream)
    except FileNotFoundError as exc:
        raise RegressionSliceError(f"regression slice file not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise RegressionSliceError(f"regression slice file is not valid JSON: {path}") from exc
    except OSError as exc:
        raise RegressionSliceError(f"unable to read regression slice file {path}") from exc

