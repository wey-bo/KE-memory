"""Phase C preregistration for the operational diagnostic profile.

Frozen *before* the fresh-hidden data exists, so the coverage requirements, the
role separation and the conclusion boundary are all committed in advance rather
than described after the numbers are known.

Why a separate preregistration rather than reusing the fresh-v3 one: fresh-v3
preregisters a 24/18 operator vocabulary and its own frozen passing chain. The
operational profile is a different, narrower vocabulary, and its qualification
must not be readable as a fresh-v3 result. Everything that can be reused *is*
reused — the scorers, the proposal freeze, the receipt and failure-freeze
machinery are untouched — so this adds a preregistration, not a harness.

Role separation is the substitute for a different author. The same controller
serializes writes, freezes and Git, but the three roles read disjoint inputs:

    author   -> writes public + authority + gold, then freezes them read-only
    proposer -> reads public only; never authority or gold
    scorer   -> reads frozen gold; never proposes

A gold path reaching the proposer would make the whole exercise self-certifying,
so that is checked rather than asserted.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


#: 本次窄域范围，与 operational-diagnostic-profile-v1 完全一致。写死在预注册里，
#: 使"评测期间悄悄扩词表"成为可检测的偏离而不是隐式变化。
PREREGISTERED_L1_OPERATOR_SENSES = (
    ("add_ingredient", "add_ingredient"),
    ("drink", "consume_beverage"),
    ("prefer", "preference_theme"),
)
PREREGISTERED_L2_OPERATOR_SENSES = (("prefer", "preference_theme"),)

#: 每个 L1 operator 必须覆盖的四类情形。
REQUIRED_L1_COVERAGE = (
    "correct_emission",
    "must_refuse_or_abstain",
    "confusable_roles_or_entities",
    "boundary_modality_polarity_time_or_lifecycle",
)
#: L2 必须覆盖的四类情形。
REQUIRED_L2_COVERAGE = (
    "multi_evidence_aggregation",
    "wrong_summary",
    "cross_turn_coreference",
    "critical_false_emission",
)

#: gold/authority 绝不允许出现在这些位置。
FORBIDDEN_GOLD_EXPOSURES = (
    "proposer_readable_path",
    "prompt",
    "environment_variable",
    "log",
    "temporary_file",
)


class RoleSeparation(StrictModel):
    """Which inputs each role may read.

    Recorded rather than assumed: the whole independence argument rests on the
    proposer never seeing gold, so the claim has to be checkable.
    """

    author_writes: tuple[str, ...] = (
        "public",
        "authority",
        "gold",
        "manifest",
    )
    proposer_reads: tuple[str, ...] = ("public",)
    scorer_reads: tuple[str, ...] = ("public", "authority", "gold", "proposal")
    controller_serializes: tuple[str, ...] = (
        "worktree_writes",
        "freezes",
        "git",
        "gates",
    )
    proposer_may_read_authority_or_gold: Literal[False] = False


class LabelGatingPolicy(StrictModel):
    """Which author judgements may gate, and which may only be observed.

    Some labels in this dataset are author conventions rather than facts. Whether
    a question counts as ``no_memory`` or ``abstain`` is the clearest case: not
    emitting is indisputable, but which non-emission label applies is a taxonomy
    choice that a real deployment might reasonably make differently.

    Gating on a convention would measure conformance to the author's taxonomy
    instead of to the evidence, and "repairing" the model to match it would be
    worse than not testing it. So the gate counts only fabrication and
    indisputable misses; convention disagreements are reported.
    """

    gated_outcomes: tuple[str, ...] = (
        "emitting_a_fact_the_text_does_not_support",
        "missing_an_indisputable_fact",
    )
    reported_not_gated_outcomes: tuple[str, ...] = (
        "choosing_the_other_non_emission_label",
        "declining_a_convention_emission",
    )
    convention_labels_may_gate: Literal[False] = False
    #: 明确禁止：不得为了让约定标签变绿而改动实现。
    repair_toward_convention_labels_authorized: Literal[False] = False


class ConclusionBoundary(StrictModel):
    """What a pass may and may not be called."""

    qualified_status: Literal["operational_diagnostic_profile_qualified"] = (
        "operational_diagnostic_profile_qualified"
    )
    l1_operator_sense_count: Literal[3] = 3
    l2_operator_sense_count: Literal[1] = 1
    implies_fresh_v3_qualified: Literal[False] = False
    implies_general_extraction_qualified: Literal[False] = False
    implies_production_ready: Literal[False] = False
    implies_benchmark_ready: Literal[False] = False
    fresh_v3_status_unchanged: Literal["not_qualified"] = "not_qualified"


class ExecutionPolicy(StrictModel):
    """One real call per layer, no retry, no repair of a frozen attempt."""

    requests_per_layer: Literal[1] = 1
    retry_same_attempt: Literal[False] = False
    fallback_model: Literal[False] = False
    authoritative_writes: Literal[False] = False
    #: 失败后允许的唯一路径。修 gold、扩词表、改评分规则或读 hidden 都不在其中。
    failure_protocol: tuple[str, ...] = (
        "freeze",
        "reproduce",
        "root_cause_analysis",
        "regression_test",
        "minimal_repair",
        "independent_review",
        "new_versioned_attempt",
    )
    forbidden_repairs: tuple[str, ...] = (
        "edit_gold",
        "widen_vocabulary",
        "change_scoring_rules",
        "read_hidden_before_scoring",
    )


class OperationalProfileFreshPreregistrationV1(StrictModel):
    """The frozen Phase C plan."""

    schema_version: Literal["operational-profile-fresh-preregistration-v1"] = (
        "operational-profile-fresh-preregistration-v1"
    )
    preregistration_id: str = Field(min_length=1)
    frozen_at: str = Field(min_length=1)
    dataset_id: str = Field(min_length=1)
    profile_id: Literal["operational-diagnostic-profile-v1"] = (
        "operational-diagnostic-profile-v1"
    )
    profile_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    ontology_registry_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    policy_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    code_sha256: dict[str, str]
    l1_operator_senses: tuple[tuple[str, str], ...] = Field(min_length=1)
    l2_operator_senses: tuple[tuple[str, str], ...] = Field(min_length=1)
    required_l1_coverage: tuple[str, ...] = Field(min_length=1)
    required_l2_coverage: tuple[str, ...] = Field(min_length=1)
    forbidden_gold_exposures: tuple[str, ...] = Field(min_length=1)
    #: 明令不得复用的既有数据集：fresh-v3 的 24/18 词汇，以及那个名字带
    #: "operational" 但实际是 fresh-v3 hidden 提案的目录。
    forbidden_input_reuse: tuple[str, ...] = (
        "typed-extractor-v3-fresh-hidden-v1",
        "typed-extractor-v3-fresh-hidden-v1-codex-gpt-operational-v1",
    )
    role_separation: RoleSeparation = Field(default_factory=RoleSeparation)
    execution_policy: ExecutionPolicy = Field(default_factory=ExecutionPolicy)
    label_gating_policy: LabelGatingPolicy = Field(
        default_factory=LabelGatingPolicy
    )
    conclusion_boundary: ConclusionBoundary = Field(
        default_factory=ConclusionBoundary
    )
    preregistration_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    def hash_body(self) -> dict[str, Any]:
        payload = self.model_dump(mode="json")
        payload.pop("preregistration_sha256", None)
        return payload

    @model_validator(mode="after")
    def validate_preregistration(
        self,
    ) -> "OperationalProfileFreshPreregistrationV1":
        if self.l1_operator_senses != PREREGISTERED_L1_OPERATOR_SENSES:
            raise ValueError("L1 vocabulary drifted from the preregistered scope")
        if self.l2_operator_senses != PREREGISTERED_L2_OPERATOR_SENSES:
            raise ValueError("L2 vocabulary drifted from the preregistered scope")
        if self.required_l1_coverage != REQUIRED_L1_COVERAGE:
            raise ValueError("L1 coverage requirements drifted")
        if self.required_l2_coverage != REQUIRED_L2_COVERAGE:
            raise ValueError("L2 coverage requirements drifted")
        if self.forbidden_gold_exposures != FORBIDDEN_GOLD_EXPOSURES:
            raise ValueError("gold exposure prohibitions drifted")
        from .authoritative_memory import canonical_sha256

        if self.preregistration_sha256 != canonical_sha256(self.hash_body()):
            raise ValueError("preregistration hash mismatch")
        return self


def _code_sha256(workspace_root: Path) -> dict[str, str]:
    """Hash the code that will produce the Phase C result.

    Frozen with the plan so a later claim of "same code" is checkable rather
    than remembered.
    """
    names = (
        "tools/natural_memory_benchmark/e2e_openai_producers.py",
        "tools/natural_memory_benchmark/e2e_pipeline.py",
        "tools/natural_memory_benchmark/typed_extractor_l1.py",
        "tools/natural_memory_benchmark/typed_extractor_l2.py",
        "tools/natural_memory_benchmark/operational_profile_fresh_prereg.py",
    )
    hashes: dict[str, str] = {}
    for name in names:
        path = workspace_root / name
        if not path.is_file():
            raise FileNotFoundError(f"code input missing: {name}")
        hashes[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    return hashes


def assert_gold_not_exposed(
    *,
    gold_paths: tuple[Path, ...],
    proposer_readable_paths: tuple[Path, ...],
    prompt_text: str,
    environment: dict[str, str] | None = None,
) -> None:
    """Refuse to proceed if gold could reach the proposer.

    Checked instead of asserted: if the proposer can read gold, a green score
    measures nothing, and that failure would be invisible in the score itself.
    """
    resolved_gold = {path.resolve() for path in gold_paths}
    for readable in proposer_readable_paths:
        resolved = readable.resolve()
        if resolved in resolved_gold:
            raise ValueError(
                "gold artifact is reachable from a proposer-readable path"
            )
        for gold in resolved_gold:
            if gold.is_relative_to(resolved):
                raise ValueError(
                    "gold artifact lies inside a proposer-readable directory"
                )
    for gold in resolved_gold:
        for fragment in (gold.name, str(gold)):
            if fragment and fragment in prompt_text:
                raise ValueError("gold artifact is named in the proposer prompt")
    for key, value in (environment if environment is not None else os.environ).items():
        for gold in resolved_gold:
            if gold.name and gold.name in value:
                raise ValueError(
                    f"gold artifact is named in environment variable {key}"
                )


def build_operational_profile_fresh_preregistration(
    *,
    workspace_root: Path,
    dataset_id: str,
    frozen_at: str,
    preregistration_id: str = "operational-profile-fresh-prereg-v1",
) -> OperationalProfileFreshPreregistrationV1:
    """Build the preregistration from the profile that will actually be used."""
    from .authoritative_memory import canonical_sha256
    from .e2e_openai_producers import (
        build_diagnostic_production_policy,
        build_extraction_profile_identity,
    )
    from .l1_ontology_linking import build_diagnostic_ontology_registry

    registry = build_diagnostic_ontology_registry()
    policy = build_diagnostic_production_policy(registry)
    profile = build_extraction_profile_identity(registry=registry, policy=policy)
    if profile.l1_operator_senses != PREREGISTERED_L1_OPERATOR_SENSES:
        raise ValueError(
            "the operational profile no longer matches the preregistered L1 scope"
        )
    if profile.l2_operator_senses != PREREGISTERED_L2_OPERATOR_SENSES:
        raise ValueError(
            "the operational profile no longer matches the preregistered L2 scope"
        )
    body: dict[str, Any] = {
        "schema_version": "operational-profile-fresh-preregistration-v1",
        "preregistration_id": preregistration_id,
        "frozen_at": frozen_at,
        "dataset_id": dataset_id,
        "profile_id": profile.profile_id,
        "profile_sha256": profile.profile_sha256,
        "ontology_registry_sha256": profile.ontology_registry_sha256,
        "policy_sha256": profile.policy_sha256,
        "code_sha256": _code_sha256(workspace_root),
        "l1_operator_senses": [list(item) for item in profile.l1_operator_senses],
        "l2_operator_senses": [list(item) for item in profile.l2_operator_senses],
        "required_l1_coverage": list(REQUIRED_L1_COVERAGE),
        "required_l2_coverage": list(REQUIRED_L2_COVERAGE),
        "forbidden_gold_exposures": list(FORBIDDEN_GOLD_EXPOSURES),
        "forbidden_input_reuse": [
            "typed-extractor-v3-fresh-hidden-v1",
            "typed-extractor-v3-fresh-hidden-v1-codex-gpt-operational-v1",
        ],
        "role_separation": RoleSeparation().model_dump(mode="json"),
        "execution_policy": ExecutionPolicy().model_dump(mode="json"),
        "label_gating_policy": LabelGatingPolicy().model_dump(mode="json"),
        "conclusion_boundary": ConclusionBoundary().model_dump(mode="json"),
    }
    return OperationalProfileFreshPreregistrationV1.model_validate(
        {**body, "preregistration_sha256": canonical_sha256(body)}
    )
