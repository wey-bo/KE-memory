"""Stage 1B: a failure-shape inventory over the lexical fixture.

Deliberately not called attribution. The observations come from a lexical fixture, not from the
real extraction, mapping, ontology, query-compilation or retrieval modules, so they locate the
shape of a failure and not its owner. Real attribution needs a per-layer trace through the
actual architecture or oracle substitution.

Splits are materialized as separate files and the discovery analysis runs in a namespace where
no other split file exists. Held-out gold is therefore unreachable rather than undeclared: an
earlier version tracked inspected ids in a list, which any code could decline to append to.

Runs without a judge.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from ke_memory_demo.evaluation.arms import (
    ArmBudget,
    turns_by_conversation,
)
from ke_memory_demo.evaluation.benchmark_loaders import load_longmemeval
from ke_memory_demo.domain import Evidence
from ke_memory_demo.evaluation.channels import (
    PublicTurn,
    assert_build_input_is_blind,
    assert_handles_are_opaque,
    session_membership,
)
from ke_memory_demo.evaluation.data_boundaries import Split, plan_splits
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
from ke_memory_demo.evaluation.split_isolation import (
    analyse_split_in_isolation,
    channels_for_split,
    materialize_splits,
)
from ke_memory_demo.request_contract import (
    RequestBudget,
    measure_request,
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

# The single request budget, shared with the answer path rather than restated here.
REQUEST_BUDGET = RequestBudget(
    context_window_tokens=128_000,
    system_reserve_tokens=116,
    output_reserve_tokens=1024,
    safety_margin_tokens=2560,
)


def _expanded_gold(
    refs: Sequence[str],
    available: Sequence[PublicTurn],
    members: Mapping[str, Sequence[str]],
) -> set[str]:
    """Resolve gold references to turn handles through published session membership."""
    handles = {t.evidence_handle for t in available}
    expanded: set[str] = set()
    for ref in refs:
        if ref in handles:
            expanded.add(ref)
            continue
        expanded.update(h for h in members.get(ref, ()) if h in handles)
    return expanded


def _as_evidence(turns: Sequence[PublicTurn]) -> list[Evidence]:
    """Present turns as Evidence so feasibility is measured on the real request shape.

    Counting a synthetic triple would repeat the mistake the contract freeze was rejected for:
    the answer path sends full Evidence records, so feasibility has to be judged on those.
    """
    return [
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
        for index, turn in enumerate(turns)
    ]


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
    # Splits become separate files; only the discovery file is ever handed to analysis.
    split_dir = Path("artifacts/stage-1b/splits")
    materialized = materialize_splits(corpus, plan, split_dir)
    discovery_file = next(m for m in materialized if m.split is Split.DISCOVERY)
    isolated = analyse_split_in_isolation(
        discovery_file,
        analysis_source=Path("tests/fixtures/split_probe.py").resolve(),
        analysis_module="split_probe",
        analysis_attr="tries_to_reach_other_splits",
    )
    if isolated.payload.get("sibling_files_reachable"):
        print(f"FAIL: sibling split files reachable: {isolated.payload}")
        return 1

    discovery_questions, discovery_gold = channels_for_split(
        corpus, plan, Split.DISCOVERY
    )


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
    for question in discovery_questions.questions:
        inspected.append(question.question_id)
        available = turns.get(question.conversation_handle, ())
        label = discovery_gold.label_for(question.question_id)
        if label is None:
            continue
        # A long conversation does not make a question infeasible: only the gold evidence
        # itself failing to fit does. Testing whole-conversation length instead conflated the
        # two and produced a context_coverage record with no basis.
        gold_turns = [
            t
            for t in available
            if t.evidence_handle in _expanded_gold(label.evidence_refs, available, members)
        ]
        delivery_infeasible = (
            bool(gold_turns)
            and measure_request(
                question.question, _as_evidence(gold_turns), REQUEST_BUDGET
            ).request_tokens
            > REQUEST_BUDGET.request_budget_tokens
        )
        trace = pipeline.run(question, available)
        observation = classify(
            question,
            label,
            available,
            trace.selected_handles,
            delivery_infeasible=delivery_infeasible,
            plan_terms=trace.plan.requested_canonical_ids,
            session_members=members,
        )
        if observation is not None:
            observations.append(observation)

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
        "split_isolation": {
            "mechanism": (
                "each split is written to its own file and analysis runs in a namespace where "
                "no other split file exists, so held-out gold is absent rather than undeclared"
            ),
            "files": [m.as_json() for m in materialized],
            "discovery_split_sha256": discovery_file.sha256,
            "sibling_files_reachable": isolated.payload.get("sibling_files_reachable", []),
            "probe_saw_repository": isolated.payload.get("repo_visible"),
            "analysis_sandbox": isolated.sandbox.as_json(),
        },
        "splits": plan.summary(),
        "split_ids": {
            "discovery_count": len(plan.ids_for(Split.DISCOVERY)),
            "validation_count": len(plan.ids_for(Split.VALIDATION)),
            "held_out_count": len(plan.ids_for(Split.HELD_OUT)),
            "excluded_retired_slice_items": excluded,
        },
        "held_out_unreachable": "structural: the held-out split file is not in the analysis namespace",
        "inspected_count": len(inspected),
        "ledger": {
            "what_this_is": "lexical-fixture failure-shape inventory, not architectural attribution",
            "observation_count": len(ledger.observations),
            "counts_by_class": counts,
            "ambiguous_count": ledger.ambiguous_count(),
            "indistinguishable_pairs": ledger.indistinguishable_pairs(),
            "ontology_primary_share": ledger.ontology_primary_share(),
            "ontology_possible_share": ledger.ontology_possible_share(),
            "share_note": (
                "the primary share counts only the forced label and reads as if the ontology "
                "were fine; the possible share is the honest figure, because it counts every "
                "observation where the ontology was never ruled out"
            ),
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
            "raw PublicTurn -> regex terms -> first lexical mapping -> lexical selection. The "
            "sandboxed builder's artifact is not consumed by this pipeline, so no observation "
            "can be attributed to real extraction, mapping, ontology, query compilation or "
            "retrieval. Attribution needs a per-layer trace or oracle substitution."
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
    print(f"ontology primary share: {ledger.ontology_primary_share():.3f}")
    print(f"ontology possible share: {ledger.ontology_possible_share():.3f}")
    for pair, count in ledger.indistinguishable_pairs().items():
        print(f"  indistinguishable: {pair} -> {count}")
    print(f"reports: {REPORT_PATH}, {LEDGER_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
