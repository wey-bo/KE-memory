"""Stage 1B: corpus-driven discovery from the frozen harness commit.

Builds the corpus once inside the sandbox, then classifies failures on the discovery split
only. The held-out split is never inspected, and that is enforced rather than asserted.

Runs without a judge. Answer quality is not measured here; what is measured is whether the
memory path can select the evidence a question needs, which is a property of extraction,
normalization, ontology coverage, planning, retrieval and closure. Separating those is the
whole point, so no observation is attributed to ontology insufficiency unless the evidence
rules the alternatives out.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ke_memory_demo.evaluation.arms import (
    ArmBudget,
    turns_by_conversation,
)
from ke_memory_demo.evaluation.benchmark_loaders import load_longmemeval
from ke_memory_demo.evaluation.channels import (
    assert_build_input_is_blind,
    assert_handles_are_opaque,
    session_membership,
)
from ke_memory_demo.evaluation.data_boundaries import (
    Split,
    assert_held_out_untouched,
    plan_splits,
)
from ke_memory_demo.evaluation.issue_ledger import (
    CLASS_EVIDENCE_REQUIREMENT,
    IssueClass,
    IssueLedger,
    classify,
)
from ke_memory_demo.evaluation.pipeline_stages import baseline_pipeline
from ke_memory_demo.evaluation.regression_slice import load_regression_slice
from ke_memory_demo.evaluation.sandboxed_build import (
    run_sandboxed_build,
    sandbox_available,
)

LONGMEMEVAL = Path("/public/home/wwb/datasets/LongMemEval/longmemeval_oracle.json")
SLICE_DIR = Path("research/next-prep/artifacts/natural-benchmark-slices/slice-v1")
REPORT_PATH = Path("artifacts/stage-1b/discovery-report.json")
LEDGER_PATH = Path("artifacts/stage-1b/issue-ledger.json")

# Dev-derived pending budget, unchanged from Stage 0.5 so discovery and the harness agree.
DELIVERY_BUDGET = ArmBudget(
    evidence_budget_tokens=24_576,
    answer_max_output_tokens=1024,
    max_evidence_units=64,
)


def main() -> int:
    if not sandbox_available():
        print("FAIL: namespace sandbox unavailable; a corpus build cannot be shown to be blind")
        return 1

    corpus = load_longmemeval(LONGMEMEVAL)
    assert_build_input_is_blind(corpus.build_input, corpus.questions, corpus.gold)
    assert_handles_are_opaque(corpus.build_input)

    # The retired slice must not reach any split. Its LongMemEval items are identified by
    # source question id, which the slice preserves in its own item ids.
    slice_bundle = load_regression_slice(SLICE_DIR)
    slice_ids = {q.question_id for q in slice_bundle.questions.questions}
    excluded = [
        q.question_id
        for q in corpus.questions.questions
        if any(q.question_id in slice_id for slice_id in slice_ids)
    ]

    plan = plan_splits(
        "longmemeval-oracle",
        [q.question_id for q in corpus.questions.questions],
        excluded_question_ids=excluded,
    )
    discovery_ids = set(plan.ids_for(Split.DISCOVERY))

    # One build, in the sandbox, from conversations only.
    build = run_sandboxed_build(
        corpus.build_input,
        builder_source=Path("src/ke_memory_demo/evaluation/stage_0_5_builder.py").resolve(),
        builder_module="stage_0_5_builder",
        builder_attr="build_memory",
    )
    if not build.sandbox.reconciled:
        print(f"FAIL: sandbox did not reconcile: {build.sandbox.reconciliation_notes}")
        return 1

    turns = turns_by_conversation(corpus.build_input)
    # Opaque handles share no prefix, so session-to-turn membership must come from the loader.
    members = session_membership(corpus.build_input)
    pipeline = baseline_pipeline()

    observations = []
    inspected: list[str] = []
    for question in corpus.questions.questions:
        if question.question_id not in discovery_ids:
            continue
        inspected.append(question.question_id)
        available = turns.get(question.conversation_handle, ())
        label = corpus.gold.label_for(question.question_id)
        if label is None:
            continue
        total_tokens = sum(t.approximate_tokens for t in available)
        trace = pipeline.run(question, available)
        observation = classify(
            question,
            label,
            available,
            trace.selected_handles,
            context_limited=total_tokens > DELIVERY_BUDGET.evidence_budget_tokens,
            plan_terms=trace.plan.requested_canonical_ids,
            session_members=members,
        )
        if observation is not None:
            observations.append(observation)

    # Mechanical proof the held-out split stayed untouched.
    assert_held_out_untouched(plan, inspected)

    ledger = IssueLedger(
        corpus_id="longmemeval-oracle",
        split=str(Split.DISCOVERY),
        observations=tuple(observations),
    )

    counts = ledger.counts()
    report: dict[str, Any] = {
        "stage": "1b",
        "status": "diagnostic_only",
        "corpus": {
            "corpus_id": "longmemeval-oracle",
            "source": str(LONGMEMEVAL),
            "conversations": len(corpus.build_input.conversations),
            "questions": len(corpus.questions.questions),
            "build_input_sha256": build.build_input_sha256,
            "memory_artifact_sha256": build.artifact_sha256,
            "single_build_rule": "one build and one extraction per frozen corpus",
        },
        "sandbox": build.sandbox.as_json(),
        "splits": plan.summary(),
        "split_ids": {
            "discovery_count": len(plan.ids_for(Split.DISCOVERY)),
            "validation_count": len(plan.ids_for(Split.VALIDATION)),
            "held_out_count": len(plan.ids_for(Split.HELD_OUT)),
            "excluded_retired_slice_items": excluded,
        },
        "held_out_untouched": True,
        "inspected_count": len(inspected),
        "ledger": {
            "observation_count": len(ledger.observations),
            "counts_by_class": counts,
            "ambiguous_count": ledger.ambiguous_count(),
            "ontology_gap_share": ledger.ontology_share(),
            "class_evidence_requirements": {
                str(cls): requirement
                for cls, requirement in CLASS_EVIDENCE_REQUIREMENT.items()
            },
        },
        "attribution_discipline": {
            "rule": "a class is assigned only when its own evidence is present",
            "ambiguity_rule": (
                "where the signals cannot separate two classes, both are recorded and the "
                "observation is marked ambiguous rather than assigned to the convenient one"
            ),
            "ontology_gap_caveat": (
                "a high ontology_gap_share is a warning about the classification, not a "
                "finding about the ontology"
            ),
        },
        "pipeline_caveat": (
            "the pipeline here is the lexical fixture, not the ontology backend, so these "
            "observations locate where a real backend must do better; they are not a "
            "measurement of the ontology"
        ),
        "judge": "not called; this track has no judge dependency",
    }

    for path, payload in (
        (REPORT_PATH, report),
        (
            LEDGER_PATH,
            {
                "corpus_id": ledger.corpus_id,
                "split": ledger.split,
                "observations": [o.model_dump(mode="json") for o in ledger.observations],
            },
        ),
    ):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=1, sort_keys=True), encoding="utf-8")

    print(f"corpus: {report['corpus']['conversations']} conversations, "
          f"{report['corpus']['questions']} questions")
    print(f"sandbox reconciled: {build.sandbox.reconciled}")
    print(
        f"splits: discovery={report['split_ids']['discovery_count']} "
        f"validation={report['split_ids']['validation_count']} "
        f"held_out={report['split_ids']['held_out_count']} "
        f"excluded={len(excluded)}"
    )
    print(f"inspected (discovery only): {len(inspected)}")
    print(f"observations: {len(ledger.observations)}")
    for cls in IssueClass:
        if counts[str(cls)]:
            print(f"  {str(cls):<24} {counts[str(cls)]}")
    print(f"ambiguous: {ledger.ambiguous_count()}")
    print(f"ontology_gap_share: {ledger.ontology_share():.3f}")
    print(f"reports: {REPORT_PATH}, {LEDGER_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
