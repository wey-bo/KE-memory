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
from pathlib import Path
from typing import Any

from ke_memory_demo.evaluation.benchmark_loaders import load_longmemeval
from ke_memory_demo.evaluation.channels import (
    assert_build_input_is_blind,
    assert_handles_are_opaque,
)
from ke_memory_demo.evaluation.data_boundaries import Split, plan_splits
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

LONGMEMEVAL = Path("/public/home/wwb/datasets/LongMemEval/longmemeval_oracle.json")
SLICE_DIR = Path("research/next-prep/artifacts/natural-benchmark-slices/slice-v1")
REPORT_PATH = Path("artifacts/stage-1b/discovery-report.json")
LEDGER_PATH = Path("artifacts/stage-1b/issue-ledger.json")

# Dev-derived pending budget, unchanged from Stage 0.5 so discovery and the harness agree.





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


    # The published analysis runs inside the sandbox on the discovery payload alone. Computing
    # observations here would put the whole corpus and all 500 gold labels in the analysing
    # process, which is what an earlier version did while isolating only a probe.
    analysis = analyse_split_in_isolation(
        discovery_file,
        analysis_source=Path(
            "src/ke_memory_demo/evaluation/sandbox_ledger_analysis.py"
        ).resolve(),
        analysis_module="sandbox_ledger_analysis",
        analysis_attr="analyse",
    )
    result = analysis.payload
    if not isinstance(result, dict):
        print("FAIL: the isolated analysis did not return a result object")
        return 1

    report: dict[str, Any] = {
        "stage": "1b",
        "status": "diagnostic_only",
        "what_this_is": result["what_this_is"],
        "corpus": {
            "corpus_id": "longmemeval-oracle",
            "source": str(LONGMEMEVAL),
            "conversations": len(corpus.build_input.conversations),
            "questions": len(corpus.questions.questions),
            "build_input_sha256": build.build_input_sha256,
            "memory_artifact_sha256": build.artifact_sha256,
            "single_build_rule": "one build and one extraction per frozen corpus",
        },
        "build_sandbox": build.sandbox.as_json(),
        "analysis_isolation": {
            "mechanism": (
                "the published analysis runs inside the namespace, receiving one split payload on "
                "stdin. The parent computes no observation, so the analysing process never holds "
                "another split's gold."
            ),
            "analysis_module": "sandbox_ledger_analysis",
            "consumed_split_sha256": analysis.consumed_split_sha256,
            "gold_labels_visible_to_analysis": result["gold_labels_visible"],
            "gold_labels_in_corpus": len(corpus.gold.labels),
            "split_files": [m.as_json() for m in materialized],
            "sibling_files_reachable": isolated.payload.get("sibling_files_reachable", []),
            "probe_saw_repository": isolated.payload.get("repo_visible"),
            "analysis_sandbox": analysis.sandbox.as_json(),
        },
        "splits": plan.summary(),
        "split_counts": {
            "discovery": len(plan.ids_for(Split.DISCOVERY)),
            "validation": len(plan.ids_for(Split.VALIDATION)),
            "held_out": len(plan.ids_for(Split.HELD_OUT)),
            "excluded_retired_slice_items": excluded,
        },
        "shape_inventory": {
            "observation_count": result["observation_count"],
            "questions_analysed": result["questions_analysed"],
            "shape_counts": result["shape_counts"],
            "possible_owner_mentions": result["possible_owner_mentions"],
            "possible_owner_share": result["possible_owner_share"],
            "no_primary_owner": (
                "possible_owners is unordered and no forced primary owner is recorded, because "
                "the real layers did not run"
            ),
        },
        "judge": "not called; this track has no judge dependency",
    }

    for path, payload in (
        (REPORT_PATH, report),
        (
            LEDGER_PATH,
            {
                "corpus_id": "longmemeval-oracle",
                "split": str(Split.DISCOVERY),
                "produced_inside_sandbox": True,
                "observations": result["observations"],
            },
        ),
    ):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=1, sort_keys=True), encoding="utf-8")

    print(f"corpus: {report['corpus']['conversations']} conversations, "
          f"{report['corpus']['questions']} questions")
    print(f"build sandbox reconciled: {build.sandbox.reconciled}")
    iso = report["analysis_isolation"]
    print(
        f"analysis isolation: gold visible to analysis "
        f"{iso['gold_labels_visible_to_analysis']} of {iso['gold_labels_in_corpus']} in corpus"
    )
    print(f"  sibling split files reachable: {iso['sibling_files_reachable']}")
    counts = report["split_counts"]
    print(
        f"splits: discovery={counts['discovery']} validation={counts['validation']} "
        f"held_out={counts['held_out']} excluded={len(counts['excluded_retired_slice_items'])}"
    )
    inv = report["shape_inventory"]
    print(f"observations: {inv['observation_count']} of {inv['questions_analysed']} analysed")
    for shape, count in inv["shape_counts"].items():
        print(f"  {shape:<38} {count}")
    print("possible owners (unordered, no primary):")
    for owner, share in inv["possible_owner_share"].items():
        print(f"  {owner:<22} share={share:.3f}")
    print(f"reports: {REPORT_PATH}, {LEDGER_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
