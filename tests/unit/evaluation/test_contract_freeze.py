"""Stage 1A contract freeze tests.

The properties worth testing here are hash independence and arithmetic self-consistency. A
test that asserts a budget equals 124285 passes for the wrong reason: it restates the number
the implementation produced and would need updating whenever the contract legitimately moved.
These tests instead perturb one input at a time and assert which hashes move.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from pydantic import ValidationError

from ke_memory_demo.evaluation.arms import (
    APPROXIMATE_TOKENIZER,
    TokenizerContract,
    turns_by_conversation,
)
from ke_memory_demo.evaluation.channels import BenchmarkQuestion, PublicTurn
from ke_memory_demo.evaluation.contract_freeze import (
    ANSWER_SYSTEM_PROMPT_PATH,
    OVER_LIMIT_STATUS,
    ContractFreeze,
    ContractFreezeError,
    OverLimitPolicyFreeze,
    ReserveFreeze,
    approximate_tokens,
    freeze_as_json,
    freeze_contracts,
    freeze_over_limit_policy,
    freeze_reserve,
    freeze_serialization,
    freeze_tokenizer,
    recompute_eligibility,
    serialize_evidence_request,
    serialize_turn,
)
from ke_memory_demo.evaluation.regression_slice import load_regression_slice

_SYSTEM_PROMPT = "Answer using only the supplied evidence.\n"
SLICE_DIR = Path("research/next-prep/artifacts/natural-benchmark-slices/slice-v1")


def _turn(handle: str, text: str, speaker: str = "user") -> PublicTurn:
    return PublicTurn(
        evidence_handle=handle,
        speaker=speaker,
        text=text,
        approximate_tokens=max(1, (len(text) + 3) // 4),
    )


def _question(question_id: str, handle: str, text: str = "What did they decide?") -> BenchmarkQuestion:
    return BenchmarkQuestion(question_id=question_id, conversation_handle=handle, question=text)


@pytest.fixture
def prompt_file(tmp_path: Path) -> Path:
    path = tmp_path / "system.md"
    path.write_text(_SYSTEM_PROMPT, encoding="utf-8")
    return path


@pytest.fixture
def models_config(tmp_path: Path) -> Path:
    path = tmp_path / "models.toml"
    path.write_text('[work]\nmodel = "deepseek-v4-flash"\n', encoding="utf-8")
    return path


@pytest.fixture
def experiment_config(tmp_path: Path) -> Path:
    path = tmp_path / "experiment.toml"
    path.write_text("[retrieval]\nanswer_max_output_tokens = 1024\n", encoding="utf-8")
    return path


def _reserve(prompt: Path, models: Path, experiment: Path) -> ReserveFreeze:
    return freeze_reserve(
        freeze_serialization(prompt),
        models_config_path=models,
        experiment_config_path=experiment,
    )


class TestTokenCounting:
    def test_count_matches_the_loader_expression(self) -> None:
        # The frozen counter must agree with the expression the regression-slice loader and
        # PublicTurn already use, or the freeze describes a different tokenizer than the one
        # that produced the numbers being frozen.
        for text in ("", "a", "abc", "abcd", "abcde", "x" * 4001, "naïve café"):
            assert approximate_tokens(text) == max(1, (len(text) + 3) // 4)

    def test_empty_text_still_costs_one_token(self) -> None:
        assert approximate_tokens("") == 1

    def test_count_scales_with_chars_per_token(self) -> None:
        eight = TokenizerContract(
            tokenizer_id="approx-chars-8", is_provider_authoritative=False, chars_per_token=8
        )
        text = "x" * 64
        assert approximate_tokens(text, eight) * 2 == approximate_tokens(text)


class TestTokenizerFreeze:
    def test_records_non_authoritative_status_and_its_consequence(self) -> None:
        frozen = freeze_tokenizer()
        assert frozen.is_provider_authoritative is False
        assert "NOT provider-authoritative" in frozen.authority_limitation
        assert "context window" in frozen.consequence

    def test_version_and_implementation_identity_are_derived(self) -> None:
        frozen = freeze_tokenizer()
        assert str(APPROXIMATE_TOKENIZER.chars_per_token) in frozen.tokenizer_version
        assert frozen.implementation_identity.endswith("approximate_tokens")
        assert frozen.parameters["chars_per_token"] == APPROXIMATE_TOKENIZER.chars_per_token

    def test_implementation_hash_digests_real_source(self) -> None:
        # The digest must cover the source of the counting functions, so an edit to the
        # arithmetic cannot leave the recorded implementation hash unchanged.
        frozen = freeze_tokenizer()
        assert frozen.implementation_sha256 != hashlib.sha256(b"").hexdigest()
        assert len(frozen.implementation_sha256) == 64

    def test_hash_moves_when_a_tokenizer_parameter_moves(self) -> None:
        other = TokenizerContract(
            tokenizer_id="approx-chars-3", is_provider_authoritative=False, chars_per_token=3
        )
        assert freeze_tokenizer().freeze_hash() != freeze_tokenizer(other).freeze_hash()

    def test_hash_is_stable_across_identical_freezes(self) -> None:
        assert freeze_tokenizer().freeze_hash() == freeze_tokenizer().freeze_hash()

    def test_provider_authoritative_tokenizer_is_rejected(self) -> None:
        # Recording this approximation as authoritative is the confusion the freeze exists to
        # prevent, so the model must refuse it rather than publish it.
        authoritative = TokenizerContract(
            tokenizer_id="deepseek-real", is_provider_authoritative=True, chars_per_token=4
        )
        with pytest.raises(ContractFreezeError, match="provider authoritative"):
            freeze_tokenizer(authoritative)


class TestSerializationFreeze:
    def test_hashes_the_real_prompt_bytes(self, prompt_file: Path) -> None:
        frozen = freeze_serialization(prompt_file)
        expected = hashlib.sha256(prompt_file.read_bytes()).hexdigest()
        assert frozen.system_prompt_sha256 == expected
        assert frozen.system_prompt_bytes == len(prompt_file.read_bytes())

    def test_repository_prompt_is_the_file_on_disk(self) -> None:
        # Freezing a prompt that is not the one the answer path loads would reserve context
        # for text that never gets sent.
        frozen = freeze_serialization()
        assert (
            frozen.system_prompt_sha256
            == hashlib.sha256(ANSWER_SYSTEM_PROMPT_PATH.read_bytes()).hexdigest()
        )

    def test_hash_moves_when_the_prompt_bytes_move(self, tmp_path: Path) -> None:
        first = tmp_path / "a.md"
        second = tmp_path / "b.md"
        first.write_text(_SYSTEM_PROMPT, encoding="utf-8")
        second.write_text(_SYSTEM_PROMPT + "Cite evidence ids.\n", encoding="utf-8")
        assert freeze_serialization(first).freeze_hash() != freeze_serialization(second).freeze_hash()

    def test_whitespace_only_prompt_change_still_moves_the_hash(self, tmp_path: Path) -> None:
        # Trailing whitespace is sent to the model and costs tokens, so it must not be
        # normalised away before hashing.
        first = tmp_path / "a.md"
        second = tmp_path / "b.md"
        first.write_text(_SYSTEM_PROMPT, encoding="utf-8")
        second.write_text(_SYSTEM_PROMPT + "\n", encoding="utf-8")
        assert freeze_serialization(first).freeze_hash() != freeze_serialization(second).freeze_hash()

    def test_empty_prompt_is_rejected(self, tmp_path: Path) -> None:
        empty = tmp_path / "empty.md"
        empty.write_bytes(b"")
        with pytest.raises(ContractFreezeError, match="must not be empty"):
            freeze_serialization(empty)

    def test_missing_prompt_is_rejected(self, tmp_path: Path) -> None:
        with pytest.raises(ContractFreezeError, match="unavailable"):
            freeze_serialization(tmp_path / "absent.md")

    def test_turn_serialization_is_deterministic_and_content_sensitive(self) -> None:
        turn = _turn("t00001", "we moved the deadline")
        assert serialize_turn(turn) == serialize_turn(turn)
        assert serialize_turn(turn) != serialize_turn(_turn("t00001", "we kept the deadline"))
        # The handle is sent, so two turns with identical text but different handles cost the
        # same only by coincidence and must not serialize identically.
        assert serialize_turn(turn) != serialize_turn(_turn("t00002", "we moved the deadline"))

    def test_turn_serialization_excludes_instrumentation_fields(self) -> None:
        frozen = freeze_serialization()
        rendered = serialize_turn(_turn("t00001", "text"))
        assert "approximate_tokens" not in rendered
        assert frozen.turn_fields_excluded == ("approximate_tokens",)
        for field in frozen.turn_field_order:
            assert f'"{field}"' in rendered

    def test_request_assembly_preserves_delivery_order(self) -> None:
        # Re-sorting evidence would disagree with what an arm recorded as delivered, so a
        # reversed sequence must produce a different request.
        first = _turn("t00001", "alpha")
        second = _turn("t00002", "beta")
        assert serialize_evidence_request("q", (first, second)) != serialize_evidence_request(
            "q", (second, first)
        )

    def test_request_assembly_includes_question_and_every_turn(self) -> None:
        rendered = serialize_evidence_request(
            "who approved it?", (_turn("t00001", "alpha"), _turn("t00002", "beta"))
        )
        assert "who approved it?" in rendered
        assert "alpha" in rendered
        assert "beta" in rendered
        assert "answer_from_evidence" in rendered

    def test_empty_envelope_costs_tokens_before_any_evidence(self) -> None:
        frozen = freeze_serialization()
        assert frozen.empty_envelope_tokens == approximate_tokens(frozen.empty_envelope_serialization)
        assert frozen.empty_envelope_tokens > 0


class TestReserveFreeze:
    def test_arithmetic_is_self_consistent(
        self, prompt_file: Path, models_config: Path, experiment_config: Path
    ) -> None:
        # The whole point of publishing the subtraction is that it can be checked, so the
        # terms must actually sum to the recorded totals.
        reserve = _reserve(prompt_file, models_config, experiment_config)
        assert (
            reserve.system_reserve_tokens
            + reserve.prompt_envelope_reserve_tokens
            + reserve.output_reserve_tokens
            + reserve.safety_margin_tokens
            == reserve.total_reserved_tokens
        )
        assert (
            reserve.context_window_tokens - reserve.total_reserved_tokens
            == reserve.evidence_budget_tokens
        )

    def test_published_arithmetic_string_contains_its_own_terms(
        self, prompt_file: Path, models_config: Path, experiment_config: Path
    ) -> None:
        reserve = _reserve(prompt_file, models_config, experiment_config)
        for term in (
            reserve.context_window_tokens,
            reserve.system_reserve_tokens,
            reserve.output_reserve_tokens,
            reserve.safety_margin_tokens,
            reserve.evidence_budget_tokens,
        ):
            assert str(term) in reserve.arithmetic
        assert reserve.arithmetic_terms["evidence_budget_tokens"] == reserve.evidence_budget_tokens

    def test_system_reserve_is_measured_from_the_frozen_prompt(
        self, prompt_file: Path, models_config: Path, experiment_config: Path
    ) -> None:
        serialization = freeze_serialization(prompt_file)
        reserve = freeze_reserve(
            serialization,
            models_config_path=models_config,
            experiment_config_path=experiment_config,
        )
        assert reserve.system_reserve_tokens == approximate_tokens(
            prompt_file.read_text(encoding="utf-8")
        )
        # The two contracts must not disagree about which prompt is in force.
        assert serialization.system_prompt_sha256[:16] in reserve.system_reserve_basis

    def test_a_longer_prompt_reserves_more_and_leaves_less(
        self, tmp_path: Path, models_config: Path, experiment_config: Path
    ) -> None:
        short = tmp_path / "short.md"
        long = tmp_path / "long.md"
        short.write_text(_SYSTEM_PROMPT, encoding="utf-8")
        long.write_text(_SYSTEM_PROMPT * 40, encoding="utf-8")
        lean = _reserve(short, models_config, experiment_config)
        heavy = _reserve(long, models_config, experiment_config)
        assert heavy.system_reserve_tokens > lean.system_reserve_tokens
        assert heavy.evidence_budget_tokens < lean.evidence_budget_tokens
        # Nothing is lost or invented by the change: the window is fully accounted for.
        assert heavy.system_reserve_tokens - lean.system_reserve_tokens == (
            lean.evidence_budget_tokens - heavy.evidence_budget_tokens
        )

    def test_output_reserve_comes_from_config_not_the_module(
        self, prompt_file: Path, models_config: Path, tmp_path: Path
    ) -> None:
        # Hardcoding 1024 here would let the freeze and the answer client disagree about the
        # answer budget without anything failing.
        altered = tmp_path / "altered.toml"
        altered.write_text("[retrieval]\nanswer_max_output_tokens = 4096\n", encoding="utf-8")
        reserve = _reserve(prompt_file, models_config, altered)
        assert reserve.output_reserve_tokens == 4096

    def test_model_id_comes_from_models_config(
        self, prompt_file: Path, experiment_config: Path, tmp_path: Path
    ) -> None:
        altered = tmp_path / "altered-models.toml"
        altered.write_text('[work]\nmodel = "some-other-model"\n', encoding="utf-8")
        reserve = _reserve(prompt_file, altered, experiment_config)
        assert reserve.model_id == "some-other-model"

    def test_repository_config_supplies_the_real_model_and_output_reserve(self) -> None:
        reserve = freeze_reserve(freeze_serialization())
        assert reserve.model_id == "deepseek-v4-flash"
        assert reserve.context_window_tokens == 128_000
        assert reserve.output_reserve_tokens == 1024

    def test_safety_margin_scales_with_its_percentage(
        self, prompt_file: Path, models_config: Path, experiment_config: Path
    ) -> None:
        serialization = freeze_serialization(prompt_file)
        margins = {
            percent: freeze_reserve(
                serialization,
                models_config_path=models_config,
                experiment_config_path=experiment_config,
                safety_margin_percent=percent,
            )
            for percent in (0, 2, 10)
        }
        assert margins[0].safety_margin_tokens == 0
        assert margins[2].safety_margin_tokens * 5 == margins[10].safety_margin_tokens
        assert margins[0].evidence_budget_tokens > margins[10].evidence_budget_tokens

    def test_hash_moves_when_the_reserve_moves(
        self, prompt_file: Path, models_config: Path, experiment_config: Path
    ) -> None:
        serialization = freeze_serialization(prompt_file)
        base = freeze_reserve(
            serialization,
            models_config_path=models_config,
            experiment_config_path=experiment_config,
        )
        wider = freeze_reserve(
            serialization,
            models_config_path=models_config,
            experiment_config_path=experiment_config,
            safety_margin_percent=5,
        )
        assert base.freeze_hash() != wider.freeze_hash()

    def test_reserve_that_exhausts_the_window_is_rejected(
        self, prompt_file: Path, models_config: Path, experiment_config: Path
    ) -> None:
        # A window smaller than the output reserve alone leaves nothing for evidence, and a
        # non-positive budget must fail loudly rather than be published.
        with pytest.raises(ContractFreezeError, match="no evidence budget"):
            freeze_reserve(
                freeze_serialization(prompt_file),
                models_config_path=models_config,
                experiment_config_path=experiment_config,
                context_window_tokens=1024,
            )

    def test_missing_configuration_is_rejected(
        self, prompt_file: Path, models_config: Path, tmp_path: Path
    ) -> None:
        with pytest.raises(ContractFreezeError, match="unavailable"):
            _reserve(prompt_file, models_config, tmp_path / "absent.toml")

    def test_arm_budget_carries_the_frozen_numbers(
        self, prompt_file: Path, models_config: Path, experiment_config: Path
    ) -> None:
        reserve = _reserve(prompt_file, models_config, experiment_config)
        budget = reserve.as_arm_budget(max_evidence_units=64)
        assert budget.evidence_budget_tokens == reserve.evidence_budget_tokens
        assert budget.answer_max_output_tokens == reserve.output_reserve_tokens


class TestOverLimitPolicy:
    def test_status_is_fixed_and_truncation_is_forbidden(self) -> None:
        policy = freeze_over_limit_policy()
        assert policy.status == OVER_LIMIT_STATUS
        assert policy.is_configurable is False
        forbidden = " ".join(policy.forbidden_behaviour).lower()
        assert "truncat" in forbidden
        assert "forbidden" in forbidden
        assert "full_history" in forbidden

    def test_a_different_status_cannot_be_recorded(self) -> None:
        # The policy is frozen to one status; a "truncate_and_report" variant must be
        # unrepresentable rather than merely discouraged.
        policy = freeze_over_limit_policy()
        with pytest.raises(ValidationError, match="fixed to"):
            OverLimitPolicyFreeze.model_validate(
                {**policy.model_dump(), "status": "truncated_full_history"}
            )

    def test_configurable_policy_is_rejected(self) -> None:
        policy = freeze_over_limit_policy()
        with pytest.raises(ValidationError, match="configurable"):
            OverLimitPolicyFreeze.model_validate(
                {**policy.model_dump(), "is_configurable": True}
            )

    def test_denominator_and_coverage_rules_are_recorded(self) -> None:
        policy = freeze_over_limit_policy()
        assert "eligible denominator" in policy.denominator_rule
        assert "coverage" in policy.reporting_requirement


class TestEligibilityRecomputation:
    def test_over_budget_items_are_ineligible_with_the_frozen_status(
        self, prompt_file: Path, models_config: Path, experiment_config: Path
    ) -> None:
        reserve = _reserve(prompt_file, models_config, experiment_config)
        small = _turn("t00001", "short")
        huge = _turn("t00002", "x" * (reserve.evidence_budget_tokens * 4 + 4000))
        result = recompute_eligibility(
            [_question("q-small", "c00001"), _question("q-huge", "c00002")],
            {"c00001": (small,), "c00002": (huge,)},
            reserve,
        )
        assert result.eligible_item_ids == ("q-small",)
        assert result.ineligible_item_ids == ("q-huge",)
        assert result.coverage == "1/2"
        statuses = {i.question_id: i.status for i in result.items}
        assert statuses["q-huge"] == OVER_LIMIT_STATUS
        assert statuses["q-small"] == "eligible"

    def test_serialized_cost_exceeds_raw_text_cost(
        self, prompt_file: Path, models_config: Path, experiment_config: Path
    ) -> None:
        # This is the substantive measurement change against Stage 0.5: JSON keys, quoting
        # and the evidence handle are sent, so they must be charged.
        reserve = _reserve(prompt_file, models_config, experiment_config)
        result = recompute_eligibility(
            [_question("q1", "c00001")],
            {"c00001": (_turn("t00001", "we moved the deadline to March"),)},
            reserve,
        )
        item = result.items[0]
        assert item.serialized_evidence_tokens > item.raw_text_tokens
        assert item.serialization_overhead_tokens == (
            item.serialized_evidence_tokens - item.raw_text_tokens
        )

    def test_question_tokens_are_charged_against_the_budget(
        self, prompt_file: Path, models_config: Path, experiment_config: Path
    ) -> None:
        reserve = _reserve(prompt_file, models_config, experiment_config)
        turns = {"c00001": (_turn("t00001", "alpha"),)}
        short = recompute_eligibility([_question("q1", "c00001", "why?")], turns, reserve)
        long = recompute_eligibility(
            [_question("q1", "c00001", "why " * 400)], turns, reserve
        )
        assert long.items[0].question_tokens > short.items[0].question_tokens
        assert long.items[0].total_request_tokens > short.items[0].total_request_tokens
        assert short.items[0].total_request_tokens == (
            short.items[0].serialized_evidence_tokens + short.items[0].question_tokens
        )

    def test_headroom_sign_matches_eligibility(
        self, prompt_file: Path, models_config: Path, experiment_config: Path
    ) -> None:
        reserve = _reserve(prompt_file, models_config, experiment_config)
        huge = _turn("t00002", "x" * (reserve.evidence_budget_tokens * 4 + 4000))
        result = recompute_eligibility(
            [_question("q-small", "c00001"), _question("q-huge", "c00002")],
            {"c00001": (_turn("t00001", "short"),), "c00002": (huge,)},
            reserve,
        )
        for item in result.items:
            assert item.eligible == (item.headroom_tokens >= 0)

    def test_counts_partition_the_item_set(
        self, prompt_file: Path, models_config: Path, experiment_config: Path
    ) -> None:
        reserve = _reserve(prompt_file, models_config, experiment_config)
        questions = [_question(f"q{i}", f"c{i:05d}") for i in range(5)]
        turns = {f"c{i:05d}": (_turn(f"t{i:05d}", "alpha beta"),) for i in range(5)}
        result = recompute_eligibility(questions, turns, reserve)
        assert result.eligible_count + result.ineligible_count == result.total_items
        assert not set(result.eligible_item_ids) & set(result.ineligible_item_ids)

    def test_a_shrinking_budget_moves_items_and_flags_the_change(
        self, prompt_file: Path, models_config: Path, experiment_config: Path
    ) -> None:
        # The delta reporting must actually detect a moved item, or an unchanged coverage
        # fraction proves nothing.
        reserve = _reserve(prompt_file, models_config, experiment_config)
        questions = [_question("q1", "c00001")]
        turns = {"c00001": (_turn("t00001", "x" * 8000),)}
        generous = recompute_eligibility(questions, turns, reserve, previous_budget_tokens=1)
        assert generous.eligible_set_changed is True
        assert generous.newly_eligible_item_ids == ("q1",)
        assert generous.newly_ineligible_item_ids == ()
        assert generous.previous_coverage == "0/1"
        assert "+1 eligible items" in generous.coverage_delta

    def test_unchanged_set_is_reported_as_unchanged(
        self, prompt_file: Path, models_config: Path, experiment_config: Path
    ) -> None:
        reserve = _reserve(prompt_file, models_config, experiment_config)
        result = recompute_eligibility(
            [_question("q1", "c00001")],
            {"c00001": (_turn("t00001", "alpha"),)},
            reserve,
        )
        assert result.eligible_set_changed is False
        assert result.newly_eligible_item_ids == ()
        assert result.newly_ineligible_item_ids == ()

    def test_an_item_with_no_turns_is_still_charged_for_its_question(
        self, prompt_file: Path, models_config: Path, experiment_config: Path
    ) -> None:
        reserve = _reserve(prompt_file, models_config, experiment_config)
        result = recompute_eligibility([_question("q1", "missing")], {}, reserve)
        item = result.items[0]
        assert item.turn_count == 0
        assert item.serialized_evidence_tokens == 0
        assert item.total_request_tokens == item.question_tokens > 0

    def test_empty_question_set_is_rejected(
        self, prompt_file: Path, models_config: Path, experiment_config: Path
    ) -> None:
        reserve = _reserve(prompt_file, models_config, experiment_config)
        with pytest.raises(ContractFreezeError, match="empty question set"):
            recompute_eligibility([], {}, reserve)


class TestHashIndependence:
    """Four hashes only help if each one tracks its own contract and nothing else."""

    @staticmethod
    def _freeze(prompt: Path, models: Path, experiment: Path) -> ContractFreeze:
        return freeze_contracts(
            [_question("q1", "c00001")],
            {"c00001": (_turn("t00001", "alpha beta"),)},
            system_prompt_path=prompt,
            models_config_path=models,
            experiment_config_path=experiment,
        )

    def test_four_distinct_hashes_are_published(
        self, prompt_file: Path, models_config: Path, experiment_config: Path
    ) -> None:
        hashes = self._freeze(prompt_file, models_config, experiment_config).hashes()
        assert len(hashes) == 4
        # Distinct values, so no two contracts share a digest and hide each other's changes.
        assert len(set(hashes.values())) == 4
        assert all(len(digest) == 64 for digest in hashes.values())

    def test_a_prompt_change_moves_serialization_and_reserve_only(
        self, tmp_path: Path, models_config: Path, experiment_config: Path
    ) -> None:
        # The reserve legitimately moves too, because it measures the prompt. The tokenizer
        # and the policy do not depend on the prompt and must not move.
        first = tmp_path / "a.md"
        second = tmp_path / "b.md"
        first.write_text(_SYSTEM_PROMPT, encoding="utf-8")
        second.write_text(_SYSTEM_PROMPT * 12, encoding="utf-8")
        before = self._freeze(first, models_config, experiment_config).hashes()
        after = self._freeze(second, models_config, experiment_config).hashes()
        assert before["serialization_sha256"] != after["serialization_sha256"]
        assert before["reserve_sha256"] != after["reserve_sha256"]
        assert before["tokenizer_sha256"] == after["tokenizer_sha256"]
        assert before["over_limit_policy_sha256"] == after["over_limit_policy_sha256"]

    def test_an_output_reserve_change_moves_the_reserve_hash_only(
        self, prompt_file: Path, models_config: Path, tmp_path: Path
    ) -> None:
        altered = tmp_path / "altered.toml"
        altered.write_text("[retrieval]\nanswer_max_output_tokens = 2048\n", encoding="utf-8")
        base = tmp_path / "base.toml"
        base.write_text("[retrieval]\nanswer_max_output_tokens = 1024\n", encoding="utf-8")
        before = self._freeze(prompt_file, models_config, base).hashes()
        after = self._freeze(prompt_file, models_config, altered).hashes()
        assert before["reserve_sha256"] != after["reserve_sha256"]
        assert before["serialization_sha256"] == after["serialization_sha256"]
        assert before["tokenizer_sha256"] == after["tokenizer_sha256"]
        assert before["over_limit_policy_sha256"] == after["over_limit_policy_sha256"]

    def test_a_tokenizer_change_moves_tokenizer_and_reserve_but_not_the_policy(
        self, prompt_file: Path, models_config: Path, experiment_config: Path
    ) -> None:
        serialization = freeze_serialization(prompt_file)
        other = TokenizerContract(
            tokenizer_id="approx-chars-8", is_provider_authoritative=False, chars_per_token=8
        )
        base_reserve = freeze_reserve(
            serialization,
            models_config_path=models_config,
            experiment_config_path=experiment_config,
        )
        other_reserve = freeze_reserve(
            serialization,
            models_config_path=models_config,
            experiment_config_path=experiment_config,
            tokenizer=other,
        )
        assert freeze_tokenizer().freeze_hash() != freeze_tokenizer(other).freeze_hash()
        assert base_reserve.freeze_hash() != other_reserve.freeze_hash()
        assert freeze_over_limit_policy().freeze_hash() == freeze_over_limit_policy().freeze_hash()

    def test_the_combined_hash_is_a_hash_of_the_four(
        self, prompt_file: Path, models_config: Path, experiment_config: Path
    ) -> None:
        freeze = self._freeze(prompt_file, models_config, experiment_config)
        combined = freeze.combined_hash()
        assert combined not in set(freeze.hashes().values())
        assert combined == self._freeze(prompt_file, models_config, experiment_config).combined_hash()

    def test_hashes_ignore_key_order(
        self, prompt_file: Path, models_config: Path, experiment_config: Path
    ) -> None:
        # Canonical JSON is what makes a digest a statement about content rather than about
        # field declaration order.
        policy = freeze_over_limit_policy()
        reordered = OverLimitPolicyFreeze.model_validate(
            dict(reversed(list(policy.model_dump().items())))
        )
        assert policy.freeze_hash() == reordered.freeze_hash()


class TestFreezeOverTheRealSlice:
    """The freeze must hold against the actual 32-item slice, not just fixtures."""

    @pytest.fixture(scope="class")
    def slice_freeze(self) -> ContractFreeze:
        loaded = load_regression_slice(SLICE_DIR)
        return freeze_contracts(
            loaded.questions.questions, turns_by_conversation(loaded.build_input)
        )

    def test_all_32_items_are_measured(self, slice_freeze: ContractFreeze) -> None:
        assert slice_freeze.eligibility.total_items == 32
        assert len(slice_freeze.eligibility.items) == 32

    def test_coverage_matches_the_ineligible_id_list(
        self, slice_freeze: ContractFreeze
    ) -> None:
        eligibility = slice_freeze.eligibility
        expected = f"{32 - len(eligibility.ineligible_item_ids)}/32"
        assert eligibility.coverage == expected

    def test_every_ineligible_item_genuinely_exceeds_the_budget(
        self, slice_freeze: ContractFreeze
    ) -> None:
        # An item excluded for any reason other than measured size would be a silent sample
        # change dressed up as a context limit.
        budget = slice_freeze.reserve.evidence_budget_tokens
        for item in slice_freeze.eligibility.items:
            if item.question_id in slice_freeze.eligibility.ineligible_item_ids:
                assert item.total_request_tokens > budget
            else:
                assert item.total_request_tokens <= budget

    def test_reserve_arithmetic_holds_on_the_real_prompt(
        self, slice_freeze: ContractFreeze
    ) -> None:
        reserve = slice_freeze.reserve
        assert (
            reserve.context_window_tokens
            - reserve.system_reserve_tokens
            - reserve.prompt_envelope_reserve_tokens
            - reserve.output_reserve_tokens
            - reserve.safety_margin_tokens
            == reserve.evidence_budget_tokens
        )

    def test_artifact_payload_carries_the_diagnostic_standing(
        self, slice_freeze: ContractFreeze
    ) -> None:
        payload = freeze_as_json(slice_freeze)
        standing = payload["metric_standing"]
        assert isinstance(standing, dict)
        assert standing["classification"] == "diagnostic_only"
        reason = standing["reason"]
        assert isinstance(reason, str)
        assert "provider-authoritative" in reason
        hashes = payload["contract_hashes"]
        assert isinstance(hashes, dict)
        for key in (
            "tokenizer_sha256",
            "serialization_sha256",
            "reserve_sha256",
            "over_limit_policy_sha256",
        ):
            assert hashes[key] == slice_freeze.hashes()[key]

    def test_freeze_is_reproducible(self, slice_freeze: ContractFreeze) -> None:
        loaded = load_regression_slice(SLICE_DIR)
        again = freeze_contracts(
            loaded.questions.questions, turns_by_conversation(loaded.build_input)
        )
        assert again.hashes() == slice_freeze.hashes()
        assert again.eligibility.coverage == slice_freeze.eligibility.coverage
