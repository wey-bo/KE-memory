"""Oracle substitution over the five-stage pipeline.

An oracle here can only be constructed if the gold for its own layer exists. That is the
structural answer to a review finding: previously four layers reused the question's final
evidence set as a stand-in for their own gold, which injected question relevance instead of
substituting the layer.

Two properties are checked rather than assumed:

- the target layer's output actually changed (a substitution that changes nothing is not a
  substitution, and the previous assertion only forbade *unrelated* change)
- no stage upstream of the target changed

Every oracle result is labelled so it can never be read as a system result.
"""

from __future__ import annotations

from collections.abc import Sequence
from enum import StrEnum
from typing import Final

from ke_memory_demo.core.json import JsonObject

from .channels import GoldChannel
from .layer_gold import LayerGold, LayerGoldBundle, LayerGoldError
from .pipeline_stages import (
    DiagnosticPipeline,
    GoldExtraction,
    GoldL2,
    GoldMapping,
    GoldQueryPlan,
    GoldSelection,
    StageTrace,
)


class OracleError(ValueError):
    """An oracle substitution was requested, combined or evidenced incorrectly."""


class OracleLayer(StrEnum):
    GOLD_EXTRACTION = "gold_extraction"
    GOLD_MEMORY_MAPPING = "gold_memory_mapping"
    GOLD_L2_ABSTRACTION = "gold_l2_abstraction"
    GOLD_QUERY_PLAN = "gold_query_plan"
    GOLD_EVIDENCE_SELECTION = "gold_evidence_selection"


ALL_ORACLE_LAYERS: tuple[OracleLayer, ...] = tuple(OracleLayer)

LAYER_FIELD: Final[dict[OracleLayer, str]] = {
    OracleLayer.GOLD_EXTRACTION: "extraction",
    OracleLayer.GOLD_MEMORY_MAPPING: "mapping",
    OracleLayer.GOLD_L2_ABSTRACTION: "l2",
    OracleLayer.GOLD_QUERY_PLAN: "query_plan",
    OracleLayer.GOLD_EVIDENCE_SELECTION: "evidence_selection",
}

# Which gold artifact each layer requires. Selection uses the gold channel; the rest need
# independently authored per-layer gold.
LAYER_GOLD_REQUIREMENT: Final[dict[OracleLayer, str]] = {
    OracleLayer.GOLD_EXTRACTION: "extraction",
    OracleLayer.GOLD_MEMORY_MAPPING: "mapping",
    OracleLayer.GOLD_L2_ABSTRACTION: "l2",
    OracleLayer.GOLD_QUERY_PLAN: "query_plan",
    OracleLayer.GOLD_EVIDENCE_SELECTION: "evidence_selection",
}

# Stage outputs that may legitimately differ once a layer is substituted: the layer itself
# plus everything downstream of it.
_STAGE_ORDER: Final[tuple[str, ...]] = (
    "extraction",
    "mapping",
    "l2",
    "query_plan",
    "evidence_selection",
)


def downstream_of(field: str) -> frozenset[str]:
    index = _STAGE_ORDER.index(field)
    allowed = set(_STAGE_ORDER[index:])
    if field == "query_plan":
        # A plan change cannot alter extraction, mapping or l2, which all precede it.
        allowed = {"query_plan", "evidence_selection"}
    return frozenset(allowed)


def substitute(
    pipeline: DiagnosticPipeline,
    layer: OracleLayer,
    *,
    layer_gold: LayerGold | None = None,
    gold: GoldChannel | None = None,
    question_id: str | None = None,
) -> DiagnosticPipeline:
    """Replace exactly one stage with its gold implementation.

    Raises when the gold that layer needs is absent, rather than silently falling back to
    a substitute derived from a different layer's annotation.
    """
    field = LAYER_FIELD[layer]

    if layer is OracleLayer.GOLD_EVIDENCE_SELECTION:
        if gold is None or question_id is None:
            raise LayerGoldError("evidence-selection oracle requires the gold channel")
        label = gold.label_for(question_id)
        if label is None:
            # Defaulting to an empty reference set silently produced selected=() and looked
            # like a legitimate abstention, so a typo in a question id became a plausible
            # result instead of an error.
            raise LayerGoldError(
                f"no gold label for question {question_id!r}; an oracle must fail closed "
                "rather than substitute an empty evidence set"
            )
        return pipeline.with_stage(field, GoldSelection(label.evidence_refs))

    if layer_gold is None:
        raise LayerGoldError(f"{layer} requires per-layer gold, which was not supplied")
    if question_id is not None and layer_gold.question_id != question_id:
        raise LayerGoldError(
            f"layer gold is for question {layer_gold.question_id!r} but the substitution is "
            f"for {question_id!r}; mismatched identity would score one question with "
            "another's gold"
        )
    required = LAYER_GOLD_REQUIREMENT[layer]
    if not layer_gold.has(required):
        raise LayerGoldError(
            f"{layer} requires {required} gold for question {layer_gold.question_id}, "
            "which is absent. Reinterpreting another layer's annotation would inject "
            "question relevance rather than substitute this layer."
        )

    if layer is OracleLayer.GOLD_EXTRACTION:
        return pipeline.with_stage(field, GoldExtraction(layer_gold))
    if layer is OracleLayer.GOLD_MEMORY_MAPPING:
        return pipeline.with_stage(field, GoldMapping(layer_gold))
    if layer is OracleLayer.GOLD_L2_ABSTRACTION:
        return pipeline.with_stage(field, GoldL2(layer_gold))
    return pipeline.with_stage(field, GoldQueryPlan(layer_gold))


def changed_stages(baseline: StageTrace, oracle: StageTrace) -> frozenset[str]:
    changed: set[str] = set()
    if baseline.unit_handles != oracle.unit_handles or [
        (u.role, u.predicate) for u in baseline.units
    ] != [(u.role, u.predicate) for u in oracle.units]:
        changed.add("extraction")
    if baseline.mapping != oracle.mapping:
        changed.add("mapping")
    if baseline.abstraction_keys != oracle.abstraction_keys or {
        a.abstraction_id: a.derived_from for a in baseline.abstractions
    } != {a.abstraction_id: a.derived_from for a in oracle.abstractions}:
        changed.add("l2")
    if baseline.plan != oracle.plan:
        changed.add("query_plan")
    if baseline.selected_handles != oracle.selected_handles:
        changed.add("evidence_selection")
    return frozenset(changed)


def assert_substitution_is_effective(
    layer: OracleLayer,
    changed: frozenset[str],
) -> None:
    """Fail unless the target layer changed and nothing upstream did.

    The positive half matters as much as the negative half. A previous version only
    forbade unrelated change, so an oracle that altered nothing at all passed silently and
    was reported as executed.
    """
    field = LAYER_FIELD[layer]
    if field not in changed:
        raise OracleError(
            f"substituting {layer} did not change the {field} stage output, so it did not "
            "substitute anything"
        )
    unexpected = sorted(changed - downstream_of(field))
    if unexpected:
        raise OracleError(f"substituting {layer} changed upstream stages: {unexpected}")


def assert_single_layer_substitution(layers: Sequence[OracleLayer]) -> None:
    if len(layers) > 1:
        raise OracleError(
            "an oracle run may substitute at most one layer; requested: "
            + ", ".join(str(layer) for layer in layers)
        )


def available_layers(
    bundle: LayerGoldBundle | None,
    *,
    gold: GoldChannel | None = None,
) -> tuple[OracleLayer, ...]:
    """Layers that can honestly be substituted with the gold actually present."""
    layers: list[OracleLayer] = []
    for layer in ALL_ORACLE_LAYERS:
        if layer is OracleLayer.GOLD_EVIDENCE_SELECTION:
            if gold is not None and gold.labels:
                layers.append(layer)
            continue
        if bundle is not None and bundle.covers(LAYER_GOLD_REQUIREMENT[layer]):
            layers.append(layer)
    return tuple(layers)


LAYER_ASSUMPTIONS: Final[dict[OracleLayer, str]] = {
    OracleLayer.GOLD_EXTRACTION: (
        "L1 extraction produced exactly the declared surface units, with correct roles and "
        "predicates"
    ),
    OracleLayer.GOLD_MEMORY_MAPPING: (
        "every surface unit mapped to the correct canonical ontology id and sense"
    ),
    OracleLayer.GOLD_L2_ABSTRACTION: (
        "cross-unit abstractions and their derivation links are correct"
    ),
    OracleLayer.GOLD_QUERY_PLAN: (
        "the question compiled to the correct frozen plan, including whether it needs an "
        "abstraction"
    ),
    OracleLayer.GOLD_EVIDENCE_SELECTION: (
        "retrieval recovered exactly the gold evidence set for the question"
    ),
}


def resolution_note(layer: OracleLayer) -> JsonObject:
    return {
        "layer": str(layer),
        "assumes_perfect": LAYER_ASSUMPTIONS[layer],
        "substitution_point": LAYER_FIELD[layer],
        "requires_gold_artifact": LAYER_GOLD_REQUIREMENT[layer],
        "is_system_result": False,
    }
