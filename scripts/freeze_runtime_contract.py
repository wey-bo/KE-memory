"""Freeze the contract the runtime actually uses, superseding the Stage 1A draft.

The earlier freeze hashed a three-field ``PublicTurn`` triple and summed per-turn rounded
estimates. This one calls the same functions the answer path calls, so the hashes move if the
runtime request shape or the enforced budget moves.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ke_memory_demo.domain import Evidence
from ke_memory_demo.evaluation.arms import turns_by_conversation
from ke_memory_demo.evaluation.regression_slice import load_regression_slice
from ke_memory_demo.evaluation.runtime_contract_freeze import (
    freeze_runtime_contract,
    measure_eligibility,
    prompt_sha256,
    system_reserve_tokens,
)

SLICE_DIR = Path("research/next-prep/artifacts/natural-benchmark-slices/slice-v1")
SUPERSEDED = Path("artifacts/stage-1a/contract-freeze.json")
OUTPUT = Path("artifacts/stage-1a/runtime-contract-freeze.json")


def main() -> int:
    superseded_hashes: dict[str, Any] = {}
    if SUPERSEDED.is_file():
        previous = json.loads(SUPERSEDED.read_text(encoding="utf-8"))
        superseded_hashes = dict(previous.get("contract_hashes", {}))

    frozen = freeze_runtime_contract(superseded_hashes=superseded_hashes)

    loaded = load_regression_slice(SLICE_DIR)
    turns = turns_by_conversation(loaded.build_input)
    questions = [(q.question_id, q.question) for q in loaded.questions.questions]
    # Turns are presented as Evidence because that is what the answer path sends; measuring a
    # synthetic triple is the mistake this freeze replaces.
    evidence_by_question = {
        q.question_id: [
            Evidence(
                evidence_id=turn.evidence_handle,
                rank=index + 1,
                score=1.0,
                channel="symbolic",
                text=turn.text,
                source_exchange_ids=(),
                source_message_ids=(),
                system_record_ids=(),
                metadata={},
                token_count=turn.approximate_tokens,
            )
            for index, turn in enumerate(turns.get(q.conversation_handle, ()))
        ]
        for q in loaded.questions.questions
    }
    eligibility = measure_eligibility(questions, evidence_by_question)

    payload: dict[str, Any] = {
        "stage": "1a-runtime",
        "standing": "diagnostic_draft_bound_to_the_runtime_path",
        "contract": frozen.as_json(),
        "measured_inputs": {
            "system_prompt_sha256": prompt_sha256(),
            "system_reserve_tokens": system_reserve_tokens(),
            "system_reserve_basis": "approximate_tokens over the real prompt bytes",
        },
        "eligibility": eligibility,
        "binding_evidence": {
            "request_builder_shared": (
                "AnswerService.request_payload delegates to request_contract.build_answer_request, "
                "so the frozen shape is the shape sent"
            ),
            "budget_enforced_in_production": frozen.budget.enforced_in_production,
            "enforcement_point": frozen.budget.enforcement_reference,
            "private_threshold_removed": (
                "the 8192-token module constant in answering.py is gone; the budget is injected "
                "and names its arm"
            ),
        },
        "residual_caveats": [
            "the tokenizer is a character approximation and is not provider authoritative, so "
            "every figure bounds instrumentation and cannot prove a request fits",
            "the 128000 context window is vendor published, not measured against the API",
            "different arms may hold different budgets; only unbound numbers are forbidden",
        ],
        "judge": "not called",
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(payload, indent=1, sort_keys=True), encoding="utf-8")

    contract = payload["contract"]
    print(f"request  sha256: {contract['request_sha256']}")
    print(f"budget   sha256: {contract['budget_sha256']}")
    print(f"evidence fields frozen: {len(frozen.request.evidence_fields)}")
    print(f"budget enforced in production: {frozen.budget.enforced_in_production}")
    print(f"budget: {frozen.budget.request_budget_tokens} | {frozen.budget.arithmetic}")
    print(
        f"eligibility: {eligibility['coverage']} | boundary "
        f"{eligibility['largest_eligible_request_tokens']} / "
        f"{eligibility['smallest_ineligible_request_tokens']}"
    )
    print(f"superseded hashes recorded: {len(superseded_hashes)}")
    print(f"artifact: {OUTPUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
