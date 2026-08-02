"""Tests for the shared request contract and structural split isolation.

Both correspond to review findings where the previous implementation looked correct:

- four contract hashes recomputed correctly while binding a synthetic ``PublicTurn`` triple that
  the answer path never sent, and three unreconciled budgets coexisted (8192, 24576, 124285)
- ``assert_held_out_untouched`` checked only the ids a caller volunteered, so any code could
  read held-out gold without declaring it
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ke_memory_demo.core.json import JsonValue, canonical_json
from ke_memory_demo.domain import Evidence
from ke_memory_demo.evaluation.benchmark_loaders import load_longmemeval
from ke_memory_demo.evaluation.data_boundaries import Split, plan_splits
from ke_memory_demo.evaluation.sandboxed_build import sandbox_available
from ke_memory_demo.evaluation.split_isolation import (
    SplitIsolationError,
    analyse_split_in_isolation,
    assert_split_file_absent,
    materialize_splits,
)
from ke_memory_demo.request_contract import (
    ANSWER_TASK,
    OverLimitPolicy,
    RequestBudget,
    RequestBuildError,
    build_answer_request,
    enforce_budget,
    measure_request,
    serialized_request_bytes,
)
from ke_memory_demo.retrieval.evidence_payload import model_evidence_payload

LONGMEMEVAL = Path("/public/home/wwb/datasets/LongMemEval/longmemeval_oracle.json")
SPLIT_PROBE = Path(__file__).resolve().parents[2] / "fixtures" / "split_probe.py"

requires_sandbox = pytest.mark.skipif(
    not sandbox_available(),
    reason="unprivileged user, mount, network and PID namespaces are unavailable",
)


def _evidence(count: int = 1, text: str = "the user moved to Berlin") -> list[Evidence]:
    return [
        Evidence(
            evidence_id=f"e{index}",
            rank=index + 1,
            score=0.9,
            channel="symbolic",
            text=text,
            source_exchange_ids=("x1",),
            source_message_ids=("m1",),
            system_record_ids=(),
            metadata={},
            token_count=8,
        )
        for index in range(count)
    ]


def test_the_request_carries_full_evidence_records_not_a_synthetic_triple() -> None:
    """The finding: the freeze hashed {handle, speaker, text} while the path sent Evidence."""
    request = build_answer_request("where does the user live", _evidence())
    assert request["task"] == ANSWER_TASK
    evidence_records = request["evidence"]
    assert isinstance(evidence_records, list)
    first = evidence_records[0]
    assert isinstance(first, dict)
    # Every Evidence field the model sees must be present, not a three-key stand-in.
    assert set(first) == {
        "evidence_id",
        "rank",
        "score",
        "channel",
        "text",
        "source_exchange_ids",
        "source_message_ids",
        "system_record_ids",
        "metadata",
    }


def test_the_builder_is_byte_identical_to_the_previous_inline_construction() -> None:
    """Delegation must not change the wire format, or the freeze would describe a new shape."""
    evidence = _evidence(2)
    previous: JsonValue = {
        "task": "answer_from_evidence",
        "question": "where does the user live",
        "evidence": list(model_evidence_payload(evidence)),
    }
    assert canonical_json(previous) == serialized_request_bytes(
        "where does the user live", evidence
    )


def test_answer_service_consumes_both_halves_of_the_contract() -> None:
    """A contract binds only if the runtime consumes it, for construction *and* enforcement.

    An earlier round shared the payload builder while leaving an 8192-token module constant and a
    private evidence-only threshold in place, so enforcement stayed unbound.
    """
    source = (
        Path(__file__).resolve().parents[3] / "src" / "ke_memory_demo" / "answering.py"
    ).read_text(encoding="utf-8")
    assert "return build_answer_request(question, ordered)" in source
    assert "enforce_budget(question, ordered, self._budget)" in source
    # The inline dict and the unbound threshold must both be gone.
    assert '"task": "answer_from_evidence"' not in source
    assert "MAX_EVIDENCE_TOKENS" not in source


def test_a_budget_names_its_arm_and_derives_its_own_arithmetic() -> None:
    budget = RequestBudget(
        arm_identity="test_arm",
        context_window_tokens=128_000,
        system_reserve_tokens=116,
        output_reserve_tokens=1024,
        safety_margin_tokens=2560,
    )
    assert budget.request_budget_tokens == 128_000 - 116 - 1024 - 2560
    assert str(budget.request_budget_tokens) in budget.arithmetic()
    # The arm identity is what stops a number being unbound; different arms may differ.
    assert budget.arm_identity in budget.arithmetic()
    assert budget.over_limit_policy is OverLimitPolicy.NOT_EXECUTED_CONTEXT_LIMIT


def test_a_budget_whose_reserves_exhaust_the_window_is_refused() -> None:
    budget = RequestBudget(
        arm_identity="test_arm",
        context_window_tokens=100,
        system_reserve_tokens=50,
        output_reserve_tokens=40,
        safety_margin_tokens=20,
    )
    with pytest.raises(RequestBuildError, match="exhaust the context window"):
        _ = budget.request_budget_tokens


def test_the_request_is_counted_once_over_the_whole_serialization() -> None:
    """Summing rounded per-component estimates drifts; the review measured -42 to +15."""
    evidence = _evidence(3)
    question = "where does the user live now"
    budget = RequestBudget(
        arm_identity="test_arm",
        context_window_tokens=128_000,
        system_reserve_tokens=116,
        output_reserve_tokens=1024,
        safety_margin_tokens=2560,
    )
    measurement = measure_request(question, evidence, budget)
    payload = serialized_request_bytes(question, evidence)

    assert measurement.serialized_bytes == len(payload)
    assert measurement.request_tokens == max(1, (len(payload) + 3) // 4)
    # A per-component sum is a different number, which is why it may not be called exact.
    per_component = sum(
        max(1, (len(canonical_json(part)) + 3) // 4)
        for part in (question, *model_evidence_payload(evidence))
    )
    assert per_component != measurement.request_tokens


def test_an_oversized_request_is_not_executed_rather_than_truncated() -> None:
    budget = RequestBudget(
        arm_identity="test_arm",
        context_window_tokens=200,
        system_reserve_tokens=10,
        output_reserve_tokens=20,
        safety_margin_tokens=5,
    )
    with pytest.raises(RequestBuildError, match="not_executed_context_limit"):
        enforce_budget("q" * 4000, _evidence(), budget)


def test_only_one_over_limit_policy_exists() -> None:
    """Truncating and continuing produced a truncated history reported as full history."""
    assert [policy.value for policy in OverLimitPolicy] == ["not_executed_context_limit"]


@pytest.mark.skipif(not LONGMEMEVAL.is_file(), reason="LongMemEval corpus not present")
def test_split_files_contain_only_their_own_questions(tmp_path: Path) -> None:
    corpus = load_longmemeval(LONGMEMEVAL)
    plan = plan_splits("lme", [q.question_id for q in corpus.questions.questions])
    materialized = materialize_splits(corpus, plan, tmp_path / "splits")

    by_split = {m.split: m for m in materialized}
    assert set(by_split) == {Split.DISCOVERY, Split.VALIDATION, Split.HELD_OUT}

    for split, entry in by_split.items():
        payload = json.loads(entry.path.read_text(encoding="utf-8"))
        own = set(plan.ids_for(split))
        present = {q["question_id"] for q in payload["questions"]}
        present |= {label["question_id"] for label in payload["gold"]}
        # A split file carrying another split's gold would defeat the whole arrangement.
        assert present <= own
        assert len(entry.sha256) == 64


def test_a_forbidden_split_file_is_refused_as_an_input(tmp_path: Path) -> None:
    held_out = tmp_path / "held_out.json"
    held_out.write_text("{}", encoding="utf-8")
    discovery = tmp_path / "discovery.json"
    discovery.write_text("{}", encoding="utf-8")

    assert_split_file_absent([discovery], Split.HELD_OUT)
    with pytest.raises(SplitIsolationError, match="held_out"):
        assert_split_file_absent([discovery, held_out], Split.HELD_OUT)


@requires_sandbox
@pytest.mark.skipif(not LONGMEMEVAL.is_file(), reason="LongMemEval corpus not present")
def test_isolated_analysis_cannot_reach_a_sibling_split(tmp_path: Path) -> None:
    """The bypass an id-declaration guard could not close.

    The probe searches for every split filename by absolute path. It finds none, because the
    directory holding them is not in its namespace.
    """
    corpus = load_longmemeval(LONGMEMEVAL)
    plan = plan_splits("lme", [q.question_id for q in corpus.questions.questions])
    materialized = materialize_splits(corpus, plan, tmp_path / "splits")
    discovery = next(m for m in materialized if m.split is Split.DISCOVERY)

    result = analyse_split_in_isolation(
        discovery,
        analysis_source=SPLIT_PROBE,
        analysis_module="split_probe",
        analysis_attr="tries_to_reach_other_splits",
    )
    payload = result.payload
    assert isinstance(payload, dict)
    assert payload["sibling_files_reachable"] == []
    assert payload["repo_visible"] is False
    assert payload["own_split"] == str(Split.DISCOVERY)
    assert result.consumed_split_sha256 == discovery.sha256
    assert result.sandbox.reconciled is True
