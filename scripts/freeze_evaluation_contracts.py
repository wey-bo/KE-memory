"""Stage 1A: freeze the evaluation contracts and recompute the eligible set.

Writes ``artifacts/stage-1a/contract-freeze.json`` with four independently hashed contracts
-- tokenizer, serialization, reserve and over-limit policy -- and the eligible set recomputed
under them.

No model call and no judge call is made. The freeze is arithmetic over the real slice, the
real system prompt bytes and the real config files; a provider round trip would add a
dependency on a service whose behaviour can change between runs, which is the opposite of
what freezing is for.

The figures written here stay diagnostic. The frozen tokenizer is a character approximation,
so it makes budgets reproducible without making them correct, and it cannot prove a request
fits the model context window.
"""

from __future__ import annotations

import json
from pathlib import Path

from ke_memory_demo.evaluation.arms import turns_by_conversation
from ke_memory_demo.evaluation.contract_freeze import (
    ContractFreeze,
    freeze_as_json,
    freeze_contracts,
)
from ke_memory_demo.evaluation.regression_slice import load_regression_slice

SLICE_DIR = Path("research/next-prep/artifacts/natural-benchmark-slices/slice-v1")
REPORT_PATH = Path("artifacts/stage-1a/contract-freeze.json")


def _build_freeze() -> ContractFreeze:
    loaded = load_regression_slice(SLICE_DIR)
    # turns_by_conversation flattens the build input the same way the arms do, so eligibility
    # is measured over exactly the evidence an arm would have been given.
    return freeze_contracts(
        loaded.questions.questions,
        turns_by_conversation(loaded.build_input),
    )


def main() -> int:
    freeze = _build_freeze()
    payload = freeze_as_json(freeze)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with REPORT_PATH.open("w", encoding="utf-8") as stream:
        json.dump(payload, stream, indent=2, ensure_ascii=False, sort_keys=True)
        stream.write("\n")

    hashes = freeze.hashes()
    print("four independent contract hashes:")
    for name, digest in hashes.items():
        print(f"  {name:<26} {digest}")

    reserve = freeze.reserve
    print(f"reserve arithmetic: {reserve.arithmetic}")
    print(
        f"  context={reserve.context_window_tokens} system={reserve.system_reserve_tokens} "
        f"envelope={reserve.prompt_envelope_reserve_tokens} "
        f"output={reserve.output_reserve_tokens} "
        f"margin={reserve.safety_margin_tokens} ({reserve.safety_margin_percent}%)"
    )

    eligibility = freeze.eligibility
    print(f"coverage: {eligibility.coverage} (was {eligibility.previous_coverage})")
    print(f"delta: {eligibility.coverage_delta}")
    print(f"eligible set changed: {eligibility.eligible_set_changed}")
    print(f"ineligible ({eligibility.ineligible_count}), status {eligibility.items[0].status!r}:")
    for item_id in eligibility.ineligible_item_ids:
        item = next(i for i in eligibility.items if i.question_id == item_id)
        print(
            f"  {item_id:<48} {item.total_request_tokens} tokens, "
            f"{-item.headroom_tokens} over budget"
        )
    print(f"boundary: {eligibility.boundary_analysis}")
    print(f"over-limit policy: {freeze.over_limit_policy.status}")
    print("standing: diagnostic_only until a provider-authoritative tokenizer replaces the")
    print("  character approximation; no model or judge call was made")
    print(f"artifact: {REPORT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
