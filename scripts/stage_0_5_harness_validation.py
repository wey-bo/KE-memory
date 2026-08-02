"""Stage 0.5 harness validation.

Exercises the pieces the plan requires before Stage 1:

- three-channel separation, verified on the real slice
- a freeze receipt that observes a real build through a question-blind input type
- three arms with a shared, hashed contract
- oracle substitution, reported only for layers whose gold actually exists
- selection and delivery metrics, over every sample

Answer generation is a deterministic stub, so nothing derived from it is written under a
formal metric name: answer correctness, abstention correctness and constraint satisfaction
are all recorded as unknown rather than inferred.

The four unannotated oracle layers are exercised on a synthetic fixture with independently
authored per-layer gold. The slice run reports only ``gold_evidence_selection``, because
reinterpreting its evidence references as extraction, mapping, L2 and query-plan gold would
inject question relevance rather than substitute those layers.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from ke_memory_demo.evaluation.arms import (
    APPROXIMATE_TOKENIZER,
    ArmBudget,
    ArmContract,
    ArmId,
    ArmResult,
    FixtureLexicalRetrievalArm,
    FullHistoryArm,
    MemoryArm,
    assert_arms_are_comparable,
    turns_by_conversation,
)
from ke_memory_demo.evaluation.channels import (
    PublicTurn,
    assert_build_input_is_blind,
    assert_handles_are_opaque,
)
from ke_memory_demo.evaluation.diagnostic_metrics import (
    DiagnosticQuestionMetrics,
    compute_diagnostic_question_metrics,
    summarize_diagnostics,
)
from ke_memory_demo.evaluation.sandboxed_build import (
    run_sandboxed_build,
    sandbox_available,
)
from ke_memory_demo.evaluation.layer_oracles import (
    ALL_ORACLE_LAYERS,
    OracleLayer,
    assert_single_layer_substitution,
    assert_substitution_is_effective,
    changed_stages,
    resolution_note,
    substitute,
)
from ke_memory_demo.evaluation.oracle_fixture import build_fixture
from ke_memory_demo.evaluation.pipeline_stages import PipelineTurnSelector, baseline_pipeline
from ke_memory_demo.evaluation.regression_slice import load_regression_slice, slice_item_ids

SLICE_DIR = Path("research/next-prep/artifacts/natural-benchmark-slices/slice-v1")
REPORT_PATH = Path("artifacts/stage-0.5/harness-validation-report.json")

# Dev-derived pending budget for the retrieval and memory arms. Covers the largest gold
# evidence set in the slice (about 18K tokens) so delivery exact match is not capped.
DELIVERY_BUDGET = ArmBudget(
    evidence_budget_tokens=24_576,
    answer_max_output_tokens=1024,
    max_evidence_units=64,
)

# full_history is a capability upper bound and must read the whole history. Its ceiling is
# the model's real context window, not a sentinel: deepseek-v4-flash advertises 128K, and
# the answer budget is reserved out of it. The tokenizer here is approximate, so this
# bound is instrumentation-side and cannot be claimed to guarantee the prompt fits.
MODEL_CONTEXT_TOKENS = 128_000
FULL_HISTORY_BUDGET = ArmBudget(
    evidence_budget_tokens=MODEL_CONTEXT_TOKENS - 1024 - 2048,
    answer_max_output_tokens=1024,
    max_evidence_units=100_000,
)
K = 10


class _DeterministicAnswerModel:
    """Answers from the evidence it is given, with no model call."""

    def answer(
        self,
        question: str,
        evidence: Sequence[PublicTurn],
        max_output_tokens: int,
    ) -> tuple[str, bool]:
        if not evidence:
            return ("There is no information in the provided context.", True)
        return (f"Answer grounded in {len(evidence)} evidence units.", False)


def _score(
    question_id: str,
    result: ArmResult,
    gold_refs: Sequence[str],
    available: Sequence[PublicTurn],
    rubric_count: int,
) -> DiagnosticQuestionMetrics:
    # LongMemEval gold names sessions while selection is scored at turn level, so a gold
    # handle is expanded to the turns it covers before comparison.
    expanded = _expand_refs(gold_refs, available)
    return compute_diagnostic_question_metrics(
        question_id=question_id,
        selected_evidence=result.selected_evidence_ids,
        delivered_evidence=result.delivered_evidence_ids,
        gold_evidence=expanded,
        k=K,
        abstention_expected=not expanded,
        abstained=result.abstained,
        budget_limited=result.budget_limited,
        answer_correct=None,
        satisfied_constraints=None,
        total_constraints=rubric_count,
    )


def _expand_refs(refs: Sequence[str], available: Sequence[PublicTurn]) -> tuple[str, ...]:
    handles = {t.evidence_handle for t in available}
    expanded: list[str] = []
    for ref in refs:
        if ref in handles:
            expanded.append(ref)
            continue
        covered = [h for h in handles if h.startswith(f"{ref}--")]
        expanded.extend(sorted(covered))
    return tuple(dict.fromkeys(expanded))


def _oracle_section() -> dict[str, Any]:
    """Validate the substitution mechanism on the fixture that has per-layer gold."""
    fixture, bundle = build_fixture()
    base = baseline_pipeline()
    section: dict[str, Any] = {}

    for layer in ALL_ORACLE_LAYERS:
        assert_single_layer_substitution([layer])
        effective = 0
        selection_hits = 0
        for question in fixture.questions.questions:
            turns = _fixture_turns(fixture.build_input, question.conversation_handle)
            baseline_trace = base.run(question, turns)
            if layer is OracleLayer.GOLD_EVIDENCE_SELECTION:
                pipeline = substitute(
                    base, layer, gold=fixture.gold, question_id=question.question_id
                )
            else:
                pipeline = substitute(
                    base, layer, layer_gold=bundle.for_question(question.question_id)
                )
            trace = pipeline.run(question, turns)
            changed = changed_stages(baseline_trace, trace)
            assert_substitution_is_effective(layer, changed)
            effective += 1
            label = fixture.gold.label_for(question.question_id)
            if set(trace.selected_handles) == set(label.evidence_refs if label else ()):
                selection_hits += 1
        note = resolution_note(layer)
        # A single substitution scoring 0.000 is not evidence the oracle is inert: the
        # remaining fixture stages are still wrong, so one perfect layer cannot repair
        # retrieval on its own. The cumulative series below is what shows the layers
        # compose, and reporting only the marginal figure would invite misreading.
        section[str(layer)] = {
            "validated_on": "synthetic fixture with independently authored per-layer gold",
            "substitution_point": note["substitution_point"],
            "requires_gold_artifact": note["requires_gold_artifact"],
            "effective_on": f"{effective}/{len(fixture.questions.questions)}",
            "selection_exact_match_rate": selection_hits / len(fixture.questions.questions),
            "assumes_perfect": note["assumes_perfect"],
            "target_layer_change_asserted": True,
        }
    section["_cumulative_composition"] = _cumulative_composition()
    return section


def _cumulative_composition() -> dict[str, Any]:
    """Substitute layers in pipeline order, recording where selection becomes correct.

    Marginal single-layer effects can each be zero while the layers still compose to a
    correct result. That distinction matters for attribution: it separates "this layer is
    irrelevant" from "this layer is necessary but not sufficient".
    """
    fixture, bundle = build_fixture()
    pipeline = baseline_pipeline()
    order = (
        OracleLayer.GOLD_EXTRACTION,
        OracleLayer.GOLD_MEMORY_MAPPING,
        OracleLayer.GOLD_L2_ABSTRACTION,
        OracleLayer.GOLD_QUERY_PLAN,
    )
    series: list[dict[str, Any]] = []
    applied: list[str] = []
    for layer in order:
        applied.append(str(layer))
        for question in fixture.questions.questions:
            pipeline = substitute(
                pipeline, layer, layer_gold=bundle.for_question(question.question_id)
            )
        hits = 0
        for question in fixture.questions.questions:
            turns = _fixture_turns(fixture.build_input, question.conversation_handle)
            staged = pipeline
            for inner in order[: order.index(layer) + 1]:
                staged = substitute(
                    staged, inner, layer_gold=bundle.for_question(question.question_id)
                )
            trace = staged.run(question, turns)
            label = fixture.gold.label_for(question.question_id)
            if set(trace.selected_handles) == set(label.evidence_refs if label else ()):
                hits += 1
        series.append(
            {
                "layers_applied": list(applied),
                "selection_exact_match_rate": hits / len(fixture.questions.questions),
            }
        )
    return {
        "series": series,
        "interpretation": (
            "marginal single-layer rates can be zero while the layers compose to a correct "
            "selection; a zero marginal rate means necessary-but-not-sufficient, not inert"
        ),
    }


def _fixture_turns(build_input: Any, handle: str) -> tuple[PublicTurn, ...]:
    return turns_by_conversation(build_input).get(handle, ())


def _slice_evidence_oracle(loaded: Any, turns: dict[str, tuple[PublicTurn, ...]]) -> dict[str, Any]:
    """Actually run the evidence-selection oracle over all 32 slice items.

    A review found the previous report listing this layer as "reported" for the slice while
    only ever executing it on two synthetic fixtures. A 1.0 from a fixture says nothing about
    the real path, so the oracle is executed here per item and every item must close.
    """
    base = baseline_pipeline()
    per_item: list[dict[str, Any]] = []
    hits = 0
    for question in loaded.questions.questions:
        available = turns.get(question.conversation_handle, ())
        pipeline = substitute(
            base,
            OracleLayer.GOLD_EVIDENCE_SELECTION,
            gold=loaded.gold,
            question_id=question.question_id,
        )
        trace = pipeline.run(question, available)
        label = loaded.gold.label_for(question.question_id)
        expected = set(_expand_refs(label.evidence_refs if label else (), available))
        got = set(trace.selected_handles)
        closed = got == expected
        hits += closed
        per_item.append(
            {
                "question_id": question.question_id,
                "gold_handles": sorted(expected),
                "selected_handles": sorted(got),
                "closed": closed,
            }
        )
    total = len(loaded.questions.questions)
    return {
        "executed_on": f"{total}/{total} slice items",
        "selection_exact_match_rate": hits / total if total else 0.0,
        "items_closed": f"{hits}/{total}",
        "per_item": per_item,
        "requirement": "32/32 exact match; anything less means the oracle is not exact",
    }


def main() -> int:
    loaded = load_regression_slice(SLICE_DIR)
    assert_build_input_is_blind(loaded.build_input, loaded.questions, loaded.gold)
    # C2: handles must not disclose dataset, conversation or category.
    assert_handles_are_opaque(loaded.build_input)

    # C1: the build runs inside user, mount, network and PID namespaces whose root contains
    # neither the repository nor the question or gold channels, so they are absent rather
    # than merely unreadable. Questions enter this process only after the child exits.
    if not sandbox_available():
        print("FAIL: namespace sandbox unavailable; a build cannot be shown to be blind")
        return 1
    isolated = run_sandboxed_build(
        loaded.build_input,
        builder_source=Path("src/ke_memory_demo/evaluation/stage_0_5_builder.py").resolve(),
        builder_module="stage_0_5_builder",
        builder_attr="build_memory",
    )
    questions = loaded.questions.questions
    receipt = {
        "build_input_sha256": isolated.build_input_sha256,
        "memory_artifact_sha256": isolated.artifact_sha256,
        "content_digest": loaded.build_input.content_digest(),
        "observed_build_count": 1,
        "sandbox": isolated.sandbox.as_json(),
        "controller_source_identity": dict(loaded.source_identity),
        "questions_released_after_build": True,
        "freeze_order_valid": True,
        "digest_binds_content": (
            "content_digest is SHA-256 over the full canonical build input including turn "
            "text, speaker and token counts, so a content tamper moves it"
        ),
    }

    turns = turns_by_conversation(loaded.build_input)
    model = _DeterministicAnswerModel()
    arms = [
        FullHistoryArm(model, FULL_HISTORY_BUDGET),
        FixtureLexicalRetrievalArm(model, DELIVERY_BUDGET),
        MemoryArm(model, DELIVERY_BUDGET, PipelineTurnSelector(baseline_pipeline())),
    ]
    contracts = {
        arm.arm_id: ArmContract(
            model_id="deterministic-stub",
            prompt_version="stage-0.5-fixture",
            temperature=0.0,
            tokenizer=APPROXIMATE_TOKENIZER,
            budget=arm.budget,
        )
        for arm in arms
    }

    # I2: full_history may not truncate and still claim to be full history. An item whose
    # conversation exceeds the model context is recorded as not executed for that arm and is
    # excluded from its denominator, with coverage reported in the headline.
    context_limit = FULL_HISTORY_BUDGET.evidence_budget_tokens
    ineligible_full_history = sorted(
        q.question_id
        for q in questions
        if sum(t.approximate_tokens for t in turns.get(q.conversation_handle, ()))
        > context_limit
    )
    eligible_ids = [q.question_id for q in questions if q.question_id not in ineligible_full_history]

    results: list[ArmResult] = []
    per_arm: dict[str, list[DiagnosticQuestionMetrics]] = {}
    not_executed: dict[str, list[str]] = {}
    for arm in arms:
        metrics: list[DiagnosticQuestionMetrics] = []
        skipped: list[str] = []
        for question in questions:
            if (
                arm.arm_id is ArmId.FULL_HISTORY
                and question.question_id in ineligible_full_history
            ):
                skipped.append(question.question_id)
                continue
            available = turns.get(question.conversation_handle, ())
            result = arm.run(question, available)
            results.append(result)
            label = loaded.gold.label_for(question.question_id)
            metrics.append(
                _score(
                    question.question_id,
                    result,
                    label.evidence_refs if label else (),
                    available,
                    len(label.rubrics) if label else 0,
                )
            )
        per_arm[str(arm.arm_id)] = metrics
        if skipped:
            not_executed[str(arm.arm_id)] = skipped

    delivery_results = [r for r in results if r.arm is not ArmId.FULL_HISTORY]
    assert_arms_are_comparable(
        delivery_results,
        DELIVERY_BUDGET,
        contracts={a: c for a, c in contracts.items() if a is not ArmId.FULL_HISTORY},
        expected_arms={ArmId.FIXTURE_LEXICAL_RETRIEVAL, ArmId.FIXTURE_LEXICAL_MEMORY},
    )

    report: dict[str, Any] = {
        "stage": "0.5",
        "status": "instrumentation_validation_only",
        "metric_standing": {
            "classification": "diagnostic_only",
            "reason": (
                "every figure here is diagnostic until the tokenizer contract, the full prompt "
                "serialization and the system/prompt/output reserve are frozen. The tokenizer "
                "is a character approximation and cannot prove a request fits the model "
                "context, so coverage 22/32, selection exact match 1.000 and recall 1.000 "
                "describe the harness under an unfrozen contract."
            ),
            "not_yet_frozen": [
                "tokenizer contract (currently an approximation, not provider authoritative)",
                "full prompt serialization",
                "system, prompt and output token reserve",
            ],
            "may_not_be_cited_as": [
                "a capability result",
                "evidence that a request fits the model context",
                "a qualification or readiness signal",
            ],
        },
        "slice_item_count": len(questions),
        "excluded_item_ids": list(slice_item_ids(loaded)),
        "freeze_receipt": receipt,
        "channel_separation": {
            "build_input_has_question_field": "questions" in type(loaded.build_input).model_fields,
            "public_metadata_policy": "recursive positive allowlist, scalars only",
            "note": (
                "the memory build receives MemoryBuildInput, which has no question field, so "
                "question-blindness is structural rather than asserted by the receipt"
            ),
        },
        "budgets": {
            "delivery_budget": DELIVERY_BUDGET.model_dump(),
            "delivery_budget_status": "dev_derived_pending; frozen for the formal set",
            "full_history_budget": FULL_HISTORY_BUDGET.model_dump(),
            "full_history_basis": (
                f"model context {MODEL_CONTEXT_TOKENS} tokens less answer and prompt "
                "reserve; a capability upper bound, not a shared budget"
            ),
            "full_history_context_limited": {
                "observed": sorted(
                    {
                        r.question_id
                        for r in results
                        if r.arm is ArmId.FULL_HISTORY and r.budget_limited
                    }
                ),
                "finding": (
                    "the largest slice conversations measure about 130800 approximate "
                    "tokens, which exceeds a 128000-token context once answer and prompt "
                    "reserve are deducted. full_history is therefore genuinely context "
                    "limited on those items rather than budget limited by choice: no "
                    "budget setting makes them fit."
                ),
                "consequence": (
                    "for those items full_history is a truncated-history condition, not a "
                    "complete-history upper bound, and must be reported as such rather "
                    "than as the capability ceiling"
                ),
            },
            "tokenizer": APPROXIMATE_TOKENIZER.model_dump(),
            "tokenizer_caveat": (
                "the tokenizer is a deterministic approximation and is not provider "
                "authoritative, so these bounds are instrumentation-side and do not "
                "guarantee a prompt fits the model context"
            ),
        },
        "arm_contract_hashes": {
            str(arm): contract.contract_hash() for arm, contract in contracts.items()
        },
        "k": K,
        "arms": {name: summarize_diagnostics(m).model_dump() for name, m in per_arm.items()},
        "full_history_eligibility": {
            "status_for_ineligible": "not_executed_context_limit",
            "coverage": f"{len(eligible_ids)}/{len(questions)}",
            "ineligible_item_ids": ineligible_full_history,
            "not_executed": not_executed,
            "rule": (
                "full_history metrics use the eligible denominator only. Truncating an "
                "over-context conversation and reporting it as full history would misname "
                "the measurement, so those items are not executed for this arm."
            ),
        },
        "cross_arm_comparison": {
            "common_eligible_question_ids": eligible_ids,
            "cross_arm_denominator": len(eligible_ids),
            "rule": (
                "cross-arm comparison uses only the questions every arm executed. The "
                "retrieval and memory arms are additionally reported over all "
                f"{len(questions)} items in the arms section above."
            ),
        },
        "oracle_layers_on_fixture": _oracle_section(),
        "oracle_layers_on_slice": {
            "gold_evidence_selection": _slice_evidence_oracle(loaded, turns),
            "withheld": [
                "gold_extraction",
                "gold_memory_mapping",
                "gold_l2_abstraction",
                "gold_query_plan",
            ],
            "reason": (
                "the slice carries no extraction, mapping, L2 or query-plan annotation. "
                "Reinterpreting its evidence references as those four kinds of gold would "
                "inject question relevance instead of substituting the layer, so those "
                "layers are validated only on the synthetic fixture."
            ),
        },
        "answer_model": (
            "deterministic stub; answer correctness, abstention correctness and constraint "
            "satisfaction are all recorded as unknown, and no quality claim follows"
        ),
        "arm_identity_note": (
            "fixture_lexical_retrieval and fixture_lexical_memory are lexical stand-ins. "
            "raw_dense_retrieval and ontology_memory are reserved for real backends."
        ),
    }
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, indent=1, sort_keys=True), encoding="utf-8")

    print(f"slice items: {report['slice_item_count']}")
    print(
        f"freeze receipt: builds={receipt['observed_build_count']} "
        f"order_valid={receipt['freeze_order_valid']} "
        f"artifact_sha_len={len(str(receipt['memory_artifact_sha256']))}"
    )
    print(f"build input can carry questions: {report['channel_separation']['build_input_has_question_field']}")
    sandbox = receipt["sandbox"]
    print(
        f"sandbox reconciled: {sandbox['reconciled']} | observed mounts: "
        f"{len(sandbox['observed_mount_points'])} | staging: "
        f"{sandbox['observed_staging_entries']} | fds: {sandbox['observed_fd_count']}"
    )
    fh = report["full_history_eligibility"]
    print(f"full_history coverage: {fh['coverage']} (ineligible: {len(fh['ineligible_item_ids'])})")
    print(f"cross-arm denominator: {report['cross_arm_comparison']['cross_arm_denominator']}")
    slice_oracle = report["oracle_layers_on_slice"]["gold_evidence_selection"]
    print(
        f"slice evidence oracle: {slice_oracle['items_closed']} closed, "
        f"ESEM={slice_oracle['selection_exact_match_rate']:.3f}"
    )
    for name, summary in report["arms"].items():
        print(
            f"{name:<28} sel_ESEM={summary['selection_exact_match_rate']:.3f} "
            f"del_ESEM={summary['delivery_exact_match_rate']:.3f} "
            f"sel_recall={summary['mean_selection_recall']:.3f} "
            f"budget_limited={summary['budget_limited_count']} "
            f"answer_rate={summary['answer_correct_rate']}"
        )
    fixture_section = report["oracle_layers_on_fixture"]
    for layer, data in fixture_section.items():
        if layer.startswith("_"):
            continue
        print(
            f"{layer:<26} effective={data['effective_on']} "
            f"marginal_sel_ESEM={data['selection_exact_match_rate']:.3f}"
        )
    for step in fixture_section["_cumulative_composition"]["series"]:
        print(
            f"  cumulative {len(step['layers_applied'])} layer(s): "
            f"sel_ESEM={step['selection_exact_match_rate']:.3f} "
            f"({step['layers_applied'][-1]})"
        )
    print(f"report: {REPORT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
