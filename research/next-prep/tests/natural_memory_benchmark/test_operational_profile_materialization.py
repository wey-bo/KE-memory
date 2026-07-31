"""物化产物必须严格区分"proposer 能看的"与"作者的判断"。

最关键的一条：public 里不得出现任何作者判断字段。如果 gold 泄漏到 proposer 的
输入里，分数就毫无意义，而这种失败在分数本身里看不出来——所以它必须被结构性
检查，而不是靠约定。

其次是 gold 必须由蓝图派生：作者手写 typed candidate 时，gold 可能与它声称
编码的散文和判定理由悄悄不一致。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tools.natural_memory_benchmark.operational_profile_fresh_authoring import (
    L1_BLUEPRINTS,
    L2_BLUEPRINTS,
    opaque_ref,
)
from tools.natural_memory_benchmark.operational_profile_fresh_materialization import (
    DATASET_ID,
    assert_public_carries_no_verdict,
    build_l1_payloads,
    build_l2_payloads,
    build_manifest,
    freeze_dataset,
)


def test_every_artifact_validates_against_the_real_scorer_models() -> None:
    """产物必须能被真正的 scorer 模型接受。

    这条是补上的缺口：此前这套测试只检查我自己造的结构，全部通过，而真实的
    `L2PublicPayload` 却拒绝了那份 payload。测自造结构不能证明 scorer 能读。
    """
    from tools.natural_memory_benchmark.typed_extractor_l1 import (
        L1AuthorityPayload,
        L1GoldPayload,
        L1Manifest,
        L1PublicPayload,
    )
    from tools.natural_memory_benchmark.typed_extractor_l2 import (
        L2AuthorityPayload,
        L2GoldPayload,
        L2Manifest,
        L2PublicPayload,
    )

    l1 = build_l1_payloads()
    L1PublicPayload.model_validate(l1["public-l1.json"])
    L1AuthorityPayload.model_validate(l1["authority-l1.json"])
    L1GoldPayload.model_validate(l1["gold-l1.json"])
    L1Manifest.model_validate(
        build_manifest(layer="l1", payloads=l1, case_count=len(L1_BLUEPRINTS))
    )

    l2 = build_l2_payloads()
    L2PublicPayload.model_validate(l2["public-l2.json"])
    L2AuthorityPayload.model_validate(l2["authority-l2.json"])
    L2GoldPayload.model_validate(l2["gold-l2.json"])
    L2Manifest.model_validate(
        build_manifest(
            layer="l2",
            payloads=l2,
            case_count=len(L2_BLUEPRINTS),
            l1_payloads=l1,
        )
    )


def test_l2_manifest_binds_its_l1_dataset() -> None:
    """L2 结果必须绑定它所依赖的那份 L1 数据，不能事后配对别的 L1。"""
    l1 = build_l1_payloads()
    manifest = build_manifest(
        layer="l2",
        payloads=build_l2_payloads(),
        case_count=len(L2_BLUEPRINTS),
        l1_payloads=l1,
    )
    assert "gold-l1.json" in manifest["l1_qualification_sha256"]
    assert "manifest-l1.json" in manifest["l1_qualification_sha256"]
    assert manifest["thresholds"]["raw_critical_false_emission_count"] == 0


def test_public_carries_no_author_verdict() -> None:
    """public 中不得出现 expected_decision / gold / rationale 等判断字段。"""
    for payloads, layer in (
        (build_l1_payloads(), "l1"),
        (build_l2_payloads(), "l2"),
    ):
        assert_public_carries_no_verdict(payloads[f"public-{layer}.json"])


def test_a_leaked_verdict_is_refused() -> None:
    """泄漏检查必须真的会拒绝，否则它只是装饰。"""
    payloads = build_l1_payloads()
    public = payloads["public-l1.json"]
    public["cases"][0]["expected_decision"] = "emit_l1"
    with pytest.raises(ValueError, match="verdict"):
        assert_public_carries_no_verdict(public)


def test_a_leaked_rationale_is_refused() -> None:
    """判定理由同样是作者判断，泄漏必须被拒。"""
    payloads = build_l1_payloads()
    public = payloads["public-l1.json"]
    public["cases"][0]["untyped_candidate"]["rationale"] = "because"
    with pytest.raises(ValueError, match="verdict"):
        assert_public_carries_no_verdict(public)


def test_public_and_gold_cover_the_same_cases() -> None:
    """public 与 gold 必须覆盖同一批 case，不能有一侧缺失。"""
    payloads = build_l1_payloads()
    public_ids = {case["case_id"] for case in payloads["public-l1.json"]["cases"]}
    gold_ids = {item["case_id"] for item in payloads["gold-l1.json"]["items"]}
    authority_ids = {
        case["case_id"] for case in payloads["authority-l1.json"]["cases"]
    }
    expected = {opaque_ref("case", item.knowledge_id) for item in L1_BLUEPRINTS}
    assert public_ids == gold_ids == authority_ids == expected


def test_gold_typed_candidate_is_derived_from_the_blueprint() -> None:
    """emit 用例的 typed candidate 必须与蓝图一致，而非手写。"""
    payloads = build_l1_payloads()
    by_case = {
        item["case_id"]: item for item in payloads["gold-l1.json"]["items"]
    }
    for blueprint in L1_BLUEPRINTS:
        gold = by_case[opaque_ref("case", blueprint.knowledge_id)]
        assert gold["expected_decision"] == blueprint.expected_decision
        typed = gold["expected_typed_candidate"]
        if blueprint.expected_decision != "emit_l1":
            assert typed is None, blueprint.knowledge_id
            continue
        assert typed["predicate"]["canonical_operator"] == (
            blueprint.canonical_operator
        )
        assert typed["predicate"]["sense"] == blueprint.predicate_sense
        assert typed["polarity"] == blueprint.polarity
        assert typed["modality"] == blueprint.modality
        assert typed["time"]["valid_time"] == blueprint.valid_time
        surfaces = {entity["surface"] for entity in typed["local_entities"]}
        assert surfaces == {
            surface for _role, surface in blueprint.role_surfaces
        }


def test_non_emission_authority_forbids_emission() -> None:
    """gold 判定不产出时，authority 必须同时禁止产出。"""
    payloads = build_l1_payloads()
    authority = {
        case["case_id"]: case for case in payloads["authority-l1.json"]["cases"]
    }
    for blueprint in L1_BLUEPRINTS:
        case = authority[opaque_ref("case", blueprint.knowledge_id)]
        assert case["emission_allowed"] == (
            blueprint.expected_decision == "emit_l1"
        ), blueprint.knowledge_id


def test_evidence_offsets_locate_the_quote() -> None:
    """证据 span 的偏移必须真的指向原文中的该段文字。"""
    payloads = build_l1_payloads()
    for case in payloads["public-l1.json"]["cases"]:
        user_text = case["source_turn"]["user"]
        for span in case["untyped_candidate"]["evidence"]:
            assert user_text[span["start"] : span["end"]] == span["quote"]


def test_manifest_binds_outputs_by_hash() -> None:
    """manifest 必须按哈希绑定三个输出，且声明 diagnostic-only。"""
    payloads = build_l1_payloads()
    manifest = build_manifest(
        layer="l1", payloads=payloads, case_count=len(L1_BLUEPRINTS)
    )
    assert set(manifest["output_sha256"]) == set(payloads)
    assert manifest["claim_boundary"]["diagnostic_only"] is True
    assert manifest["claim_boundary"]["automatic_authoritative_writes"] is False
    assert manifest["dataset_id"] == DATASET_ID


def test_manifest_hash_changes_when_a_payload_changes() -> None:
    """输出变化必须改变 manifest 哈希，否则漂移不可检测。"""
    payloads = build_l1_payloads()
    baseline = build_manifest(
        layer="l1", payloads=payloads, case_count=len(L1_BLUEPRINTS)
    )
    mutated = build_l1_payloads()
    mutated["gold-l1.json"]["items"][0]["expected_decision"] = "abstain"
    changed = build_manifest(
        layer="l1", payloads=mutated, case_count=len(L1_BLUEPRINTS)
    )
    assert changed["output_sha256"] != baseline["output_sha256"]


def test_freeze_writes_read_only_and_refuses_overwrite(tmp_path: Path) -> None:
    """产物必须写为只读，且拒绝覆盖已存在的数据集。"""
    root = tmp_path / "dataset"
    written = freeze_dataset(root)
    assert len(written) == 8, sorted(written)
    for name in written:
        path = root / name
        assert path.is_file()
        assert path.stat().st_mode & 0o222 == 0, name
    with pytest.raises(ValueError, match="already populated"):
        freeze_dataset(root)


def test_l2_support_pack_has_at_least_two_supports(tmp_path: Path) -> None:
    """L2 是跨轮抽象，支撑必须至少两条。"""
    payloads = build_l2_payloads()
    for case in payloads["public-l2.json"]["cases"]:
        assert len(case["typed_l1_support_pack"]) >= 2, case["case_id"]
        assert len(case["source_turns"]) >= 2, case["case_id"]
    assert len(payloads["gold-l2.json"]["items"]) == len(L2_BLUEPRINTS)
