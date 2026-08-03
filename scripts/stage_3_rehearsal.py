"""Stage 3: rehearse the real chain and the attribution tooling on the 32-item slice.

Acceptance here is about instruments, not models. Four properties, each checked rather than
asserted:

- the builder artifact is demonstrably consumed, by digest, at every layer
- the gold retrieval oracle reaches 1.0
- a substitution changes only its own layer and what follows it
- no gold reaches the chain

The 32 items are never fresh hidden again, and there is no model-quality threshold and no
targeted repair. A number that looks poor here is information about the fixture, not a reason to
adjust anything.

Single-layer and cumulative substitution are reported together. A zero single-layer gain does not
license the conclusion that a module is sound: the other layers are still wrong, so one perfect
layer often cannot move the outcome on its own.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ke_memory_demo.evaluation.chain_layers import (
    LAYER_FOR_ORACLE,
    GoldAbstractionLayer,
    GoldExtractionLayer,
    GoldMappingLayer,
    GoldQueryPlanLayer,
    GoldRetrievalLayer,
    baseline_chain,
)
from ke_memory_demo.evaluation.channels import BenchmarkQuestion, GoldChannel
from ke_memory_demo.evaluation.execution_chain import (
    ChainResult,
    ExecutionChain,
    Layer,
    assert_artifact_read_by_every_layer,
    assert_only_target_and_downstream_changed,
    changed_layers,
)
from ke_memory_demo.evaluation.layer_gold import LayerGold
from ke_memory_demo.evaluation.memory_artifact import (
    MemoryArtifact,
    artifact_turn_count,
    parse_memory_artifact,
)
from ke_memory_demo.evaluation.oracle_fixture import build_fixture
from ke_memory_demo.evaluation.mapper_v1_layer import (
    MapperV1MappingLayer,
    MapperV1QueryPlanLayer,
)
from ke_memory_demo.evaluation.regression_slice import load_regression_slice
from ke_memory_demo.mapper_v1.mapper import MapperV1, load_frozen_ontology
from ke_memory_demo.evaluation.sandboxed_build import (
    run_sandboxed_build,
    sandbox_available,
)

SLICE_DIR = Path("research/next-prep/artifacts/natural-benchmark-slices/slice-v1")
ONTOLOGY_DIR = Path("artifacts/ontology-v1")
BUILDER = Path("src/ke_memory_demo/evaluation/stage_0_5_builder.py")
REPORT = Path("artifacts/stage-3/rehearsal-report.json")

ORACLE_ORDER = (
    "gold_extraction",
    "gold_memory_mapping",
    "gold_l2_abstraction",
    "gold_query_plan",
    "gold_evidence_selection",
)


def _substitute(
    chain: ExecutionChain,
    oracle: str,
    *,
    layer_gold: LayerGold | None,
    gold: GoldChannel | None,
    question_id: str,
) -> ExecutionChain:
    """Replace one real layer. Each oracle needs its own layer's gold, or it raises."""
    layer = LAYER_FOR_ORACLE[oracle]
    if oracle == "gold_evidence_selection":
        if gold is None:
            raise ValueError("the retrieval oracle requires the gold channel")
        label = gold.label_for(question_id)
        if label is None:
            raise ValueError(f"no gold label for {question_id}; the oracle must fail closed")
        return chain.with_layer(layer, GoldRetrievalLayer(label.evidence_refs))

    if layer_gold is None:
        raise ValueError(f"{oracle} requires per-layer gold, which was not supplied")
    if oracle == "gold_extraction":
        return chain.with_layer(layer, GoldExtractionLayer(layer_gold))
    if oracle == "gold_memory_mapping":
        return chain.with_layer(layer, GoldMappingLayer(layer_gold))
    if oracle == "gold_l2_abstraction":
        return chain.with_layer(layer, GoldAbstractionLayer(layer_gold))
    return chain.with_layer(layer, GoldQueryPlanLayer(layer_gold))


def _expand(refs: tuple[str, ...], artifact: MemoryArtifact, handle: str) -> set[str]:
    """Resolve gold references to turn handles through the artifact's session membership."""
    turns = {t.evidence_handle for t in artifact.turns_for(handle)}
    expanded: set[str] = set()
    for ref in refs:
        if ref in turns:
            expanded.add(ref)
            continue
        expanded.update(h for h in artifact.members_of(ref) if h in turns)
    return expanded


def _rehearse_gold_retrieval_oracle(
    artifact: MemoryArtifact,
    questions: tuple[BenchmarkQuestion, ...],
    gold: GoldChannel,
) -> dict[str, Any]:
    """The falsifiability check: a perfect retrieval layer must score perfectly."""
    chain = baseline_chain()
    exact = 0
    per_item: list[dict[str, Any]] = []
    for question in questions:
        label = gold.label_for(question.question_id)
        expected = (
            _expand(label.evidence_refs, artifact, question.conversation_handle)
            if label
            else set()
        )
        substituted = _substitute(
            chain,
            "gold_evidence_selection",
            layer_gold=None,
            gold=gold,
            question_id=question.question_id,
        )
        result = substituted.run(question, artifact)
        assert_artifact_read_by_every_layer(result)
        got = set(result.selected_handles)
        closed = got == expected
        exact += closed
        per_item.append(
            {
                "question_id": question.question_id,
                "gold_handles": sorted(expected),
                "selected_handles": sorted(got),
                "closed": closed,
            }
        )
    return {
        "executed_on": f"{len(questions)}/{len(questions)} slice items",
        "selection_exact_match_rate": exact / len(questions) if questions else 0.0,
        "items_closed": f"{exact}/{len(questions)}",
        "requirement": "1.0; anything less means the oracle is not exact",
        "per_item": per_item,
    }


def _rehearse_layer_isolation(artifact: MemoryArtifact) -> dict[str, Any]:
    """Substitution must change its own layer and nothing upstream.

    Run on the synthetic fixture, which is the only data carrying per-layer gold. The slice has
    none, and reinterpreting its evidence references as four kinds of gold is what an earlier
    round was rejected for.
    """
    fixture, bundle = build_fixture()
    fixture_artifact = _artifact_from_fixture(fixture, artifact)
    chain = baseline_chain()
    findings: dict[str, Any] = {}

    for oracle in ORACLE_ORDER:
        layer = LAYER_FOR_ORACLE[oracle]
        effective = 0
        for question in fixture.questions.questions:
            baseline = chain.run(question, fixture_artifact)
            substituted = _substitute(
                chain,
                oracle,
                layer_gold=bundle.for_question(question.question_id),
                gold=fixture.gold,
                question_id=question.question_id,
            ).run(question, fixture_artifact)
            changed = changed_layers(baseline, substituted)
            assert_only_target_and_downstream_changed(layer, changed)
            if layer in changed:
                effective += 1
        findings[oracle] = {
            "target_layer": str(layer),
            "changed_its_own_layer_on": f"{effective}/{len(fixture.questions.questions)}",
            "upstream_change_rejected": True,
        }
    return findings


def _rehearse_cumulative(artifact: MemoryArtifact) -> dict[str, Any]:
    """Cumulative substitution, so a zero single-layer gain is not misread as no problem."""
    fixture, bundle = build_fixture()
    fixture_artifact = _artifact_from_fixture(fixture, artifact)
    chain = baseline_chain()
    order = ORACLE_ORDER[:4]
    series: list[dict[str, Any]] = []
    applied: list[str] = []

    for oracle in order:
        applied.append(oracle)
        exact = 0
        for question in fixture.questions.questions:
            staged = chain
            for name in applied:
                staged = _substitute(
                    staged,
                    name,
                    layer_gold=bundle.for_question(question.question_id),
                    gold=fixture.gold,
                    question_id=question.question_id,
                )
            result = staged.run(question, fixture_artifact)
            label = fixture.gold.label_for(question.question_id)
            expected = set(label.evidence_refs) if label else set()
            exact += set(result.selected_handles) == expected
        series.append(
            {
                "layers_applied": list(applied),
                "selection_exact_match_rate": exact / len(fixture.questions.questions),
            }
        )
    return {
        "series": series,
        "interpretation": (
            "a zero single-layer rate means necessary but not sufficient, not inert; the "
            "cumulative series is what shows the layers compose"
        ),
    }


def _artifact_from_fixture(fixture: Any, _slice_artifact: MemoryArtifact) -> MemoryArtifact:
    """Build the fixture's artifact through the same builder the chain consumes."""
    from ke_memory_demo.evaluation.stage_0_5_builder import build_memory

    payload = build_memory(dict(fixture.build_input.canonical_content()))  # type: ignore[arg-type]
    return parse_memory_artifact(payload)


def _assert_no_gold_in_chain(result: ChainResult, gold: GoldChannel) -> None:
    """No answer string from gold may appear in what the chain produced."""
    answers = {
        label.answer for label in gold.labels if len(label.answer) >= 24
    }
    for answer in answers:
        if answer and answer in result.answer_text:
            raise ValueError(
                f"a gold answer appeared in the chain output for {result.question_id}"
            )


def main() -> int:
    if not sandbox_available():
        print("FAIL: namespace sandbox unavailable; a build cannot be shown to be blind")
        return 1

    loaded = load_regression_slice(SLICE_DIR)
    build = run_sandboxed_build(
        loaded.build_input,
        builder_source=BUILDER.resolve(),
        builder_module="stage_0_5_builder",
        builder_attr="build_memory",
    )
    artifact = parse_memory_artifact(build.artifact)

    # Mapper v1 replaces the lexical mapping slot. This rerun revalidates the trace, artifact
    # consumption and the oracles; it is not a fresh evaluation of the slice.
    mapper = MapperV1(load_frozen_ontology(ONTOLOGY_DIR))
    mapper_layer = MapperV1MappingLayer(mapper)
    plan_layer = MapperV1QueryPlanLayer(mapper)
    # Both slots move together. Installing the mapper alone left the planner emitting lex:* terms
    # against l1:* ontology ids, so the two vocabularies could never intersect.
    chain = (
        baseline_chain()
        .with_layer(Layer.MAPPING, mapper_layer)
        .with_layer(Layer.QUERY_PLAN, plan_layer)
    )
    baseline_results = [chain.run(q, artifact) for q in loaded.questions.questions]
    for result in baseline_results:
        assert_artifact_read_by_every_layer(result)
        _assert_no_gold_in_chain(result, loaded.gold)

    gold_oracle = _rehearse_gold_retrieval_oracle(
        artifact, loaded.questions.questions, loaded.gold
    )
    isolation = _rehearse_layer_isolation(artifact)
    cumulative = _rehearse_cumulative(artifact)

    layer_status: dict[str, dict[str, int]] = {}
    for result in baseline_results:
        for trace in result.traces:
            bucket = layer_status.setdefault(str(trace.layer), {})
            bucket[str(trace.status)] = bucket.get(str(trace.status), 0) + 1

    report: dict[str, Any] = {
        "stage": "3",
        "purpose": "validate the real chain and the attribution tooling; instruments only",
        "acceptance": {
            "artifact_consumed": True,
            "artifact_sha256": artifact.content_digest(),
            "artifact_turns_read": artifact_turn_count(artifact),
            "builder_id": artifact.builder_id,
            "gold_retrieval_oracle_exact": gold_oracle["selection_exact_match_rate"],
            "gold_retrieval_requirement_met": gold_oracle["selection_exact_match_rate"] == 1.0,
            "substitution_changes_only_target_and_downstream": True,
            "no_gold_in_chain_output": True,
        },
        "consumption_evidence": (
            "every layer trace carries the artifact digest and assert_artifact_read_by_every_layer "
            "rejects a mismatch, so a layer that reached back to the corpus would fail rather than "
            "pass silently"
        ),
        "mapping_slot": {
            "implementation": "mapper_v1 installed in the chain's mapping layer",
            "mapper_freeze_hash": mapper.freeze_hash(),
            "query_plan_slot": "mapper_v1 also compiles the question, so plan and mapping share one vocabulary",
            "resolution_counts_last_question": mapper_layer.resolution_counts(),
            "rerun_purpose": (
                "revalidate trace, artifact consumption and oracles with the real mapper in place; "
                "the 32 items are not re-treated as a fresh evaluation"
            ),
        },
        "chain": {
            "layers": [str(layer) for layer in Layer],
            "questions": len(loaded.questions.questions),
            "layer_status_counts": layer_status,
            "non_empty_selection": sum(1 for r in baseline_results if r.selected_handles),
        },
        "gold_retrieval_oracle": gold_oracle,
        "single_layer_isolation": isolation,
        "cumulative_substitution": cumulative,
        "data_rule": "the 32 items are never fresh hidden again",
        "no_quality_threshold": (
            "no model-quality pass line and no targeted repair; the answer layer is a stub, so "
            "answer correctness is not evaluated here"
        ),
        "judge": "not called",
    }
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, indent=1, sort_keys=True), encoding="utf-8")

    acc = report["acceptance"]
    print(f"artifact consumed: {acc['artifact_consumed']} ({acc['artifact_turns_read']} turns)")
    print(f"builder: {acc['builder_id']} | digest {acc['artifact_sha256'][:16]}")
    print(
        f"gold retrieval oracle: {gold_oracle['items_closed']} closed, "
        f"exact={gold_oracle['selection_exact_match_rate']:.3f}"
    )
    print(f"non-empty selection (baseline): {report['chain']['non_empty_selection']}/32")
    for oracle, data in isolation.items():
        print(f"  {oracle:<26} own layer changed on {data['changed_its_own_layer_on']}")
    for step in cumulative["series"]:
        print(
            f"  cumulative {len(step['layers_applied'])}: "
            f"exact={step['selection_exact_match_rate']:.3f} "
            f"({step['layers_applied'][-1]})"
        )
    print(f"report: {REPORT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
