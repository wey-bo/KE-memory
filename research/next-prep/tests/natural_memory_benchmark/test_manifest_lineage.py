"""manifest 必须描述它实际打包的那批用例。

审计发现：`build_manifest` 无论传入哪一版 blueprints，都调用全局 v1 的
`coverage_report()` 与 `label_confidence_report()`。于是 hidden-v3 的 manifest 里
出现的是 `op-l1-*` 旧 ID，`authored_blueprints` hash 也不是 v3 的摘要。

冻结的 public/gold 输出 hash 仍然有效——那些是对实际字节算的——但 manifest 的
自描述与 lineage 是错的。一份说不清自己装了什么的 manifest，无法用来核对某次
评分跑的是哪批数据。
"""

from __future__ import annotations

from tools.natural_memory_benchmark.operational_profile_fresh_authoring import (
    L1_BLUEPRINTS,
    coverage_report,
    label_confidence_report,
)
from tools.natural_memory_benchmark.operational_profile_fresh_authoring_v3 import (
    DATASET_ID as V3_DATASET_ID,
    L1_BLUEPRINTS_V3,
    L2_BLUEPRINTS_V3,
    coverage_report_v3,
)
from tools.natural_memory_benchmark.operational_profile_fresh_materialization import (
    build_l1_payloads,
    build_manifest,
)


def _v3_reports() -> dict[str, object]:
    return {
        "coverage": coverage_report_v3(),
        "label_confidence": {
            "indisputable_case_ids": sorted(
                item.knowledge_id
                for item in (*L1_BLUEPRINTS_V3, *L2_BLUEPRINTS_V3)
                if item.label_confidence == "indisputable"
            ),
            "convention_case_ids": sorted(
                item.knowledge_id
                for item in (*L1_BLUEPRINTS_V3, *L2_BLUEPRINTS_V3)
                if item.label_confidence == "convention"
            ),
            "gate_counts_only_indisputable_violations": True,
            "convention_labels_are_reported_not_gated": True,
        },
    }


def test_manifest_describes_the_blueprints_it_was_given() -> None:
    """传入 v3 报告时，manifest 里只能出现 v3 的 case ID。"""
    payloads = build_l1_payloads(
        blueprints=L1_BLUEPRINTS_V3, dataset_id=V3_DATASET_ID
    )
    manifest = build_manifest(
        layer="l1",
        payloads=payloads,
        case_count=len(L1_BLUEPRINTS_V3),
        dataset_id=V3_DATASET_ID,
        blueprint_reports=_v3_reports(),
    )
    ids = manifest["distribution"]["label_confidence"]["indisputable_case_ids"]
    assert ids, "manifest must list the cases it packages"
    assert all(item.startswith("op3-") for item in ids), ids
    assert not any(item.startswith("op-l1-") for item in ids), ids
    assert manifest["distribution"]["coverage"]["dataset_id"] == V3_DATASET_ID


def test_the_blueprint_hash_follows_the_reports() -> None:
    """authored_blueprints hash 必须随所描述的用例集变化。"""
    payloads = build_l1_payloads(
        blueprints=L1_BLUEPRINTS_V3, dataset_id=V3_DATASET_ID
    )
    v3 = build_manifest(
        layer="l1",
        payloads=payloads,
        case_count=len(L1_BLUEPRINTS_V3),
        dataset_id=V3_DATASET_ID,
        blueprint_reports=_v3_reports(),
    )
    v1_default = build_manifest(
        layer="l1",
        payloads=payloads,
        case_count=len(L1_BLUEPRINTS_V3),
        dataset_id=V3_DATASET_ID,
    )
    assert (
        v3["input_sha256"]["authored_blueprints"]
        != v1_default["input_sha256"]["authored_blueprints"]
    )


def test_the_default_still_describes_v1() -> None:
    """不传报告时沿用 v1，保证既有 v1 manifest 可复现。"""
    payloads = build_l1_payloads()
    manifest = build_manifest(
        layer="l1", payloads=payloads, case_count=len(L1_BLUEPRINTS)
    )
    expected = {
        "coverage": coverage_report(),
        "label_confidence": label_confidence_report(),
    }
    assert manifest["distribution"] == expected


def test_the_frozen_v3_manifest_is_known_to_be_inaccurate() -> None:
    """已冻结的 v3 manifest 确实带着 v1 标签清单，这一事实必须被固定。

    冻结字节不得改写，所以这里断言的是"缺陷存在且已被记录"，修正以追加文件的
    形式提供。
    """
    import json
    from pathlib import Path

    frozen = (
        Path(__file__).resolve().parents[2]
        / "artifacts/automatic-extraction-assessment"
        / "operational-profile-fresh-hidden-v3/manifest-l1.json"
    )
    payload = json.loads(frozen.read_text(encoding="utf-8"))
    ids = payload["distribution"]["label_confidence"]["indisputable_case_ids"]
    assert payload["dataset_id"] == V3_DATASET_ID
    # 缺陷的证据：dataset_id 是 v3，标签清单却是 v1 的。
    assert any(item.startswith("op-l1-") for item in ids)
    assert not any(item.startswith("op3-") for item in ids)
    correction = frozen.with_name("manifest-correction.json")
    assert correction.is_file(), "an appended correction must accompany the defect"
    fixed = json.loads(correction.read_text(encoding="utf-8"))
    assert fixed["corrects"] == ["manifest-l1.json", "manifest-l2.json"]
    assert fixed["frozen_files_modified"] is False
    corrected_ids = fixed["corrected_distribution"]["label_confidence"][
        "indisputable_case_ids"
    ]
    assert all(item.startswith("op3-") for item in corrected_ids)
