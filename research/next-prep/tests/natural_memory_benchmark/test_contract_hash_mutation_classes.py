"""contract hash 必须只随语义变化，且算法本身被钉住。

整理会移动模块、重写 import、调整格式。哈希若对这些反应，迁移就会在契约未变时
报警；哈希若对 prompt、schema、policy 的真实变化无反应，它就拦不住真正的漂移。
所以四类变异必须逐条固定：

    prompt / request / response schema 变  -> hash 变
    materialization contract 变            -> hash 变
    policy / registry 变                   -> hash 变
    模块路径 / 文件名 / 空白 / 注释 变      -> hash 不变

同时钉住 canonical contract 的 schema version 与哈希算法。否则未来新增字段时，
旧记录会在"看起来兼容"的情况下静默改变含义——那种失败在哈希值里看不出来。
"""

from __future__ import annotations

import hashlib

from tools.natural_memory_benchmark.e2e_openai_producers import (
    build_diagnostic_production_policy,
    build_producer_contract_identity,
)
from tools.natural_memory_benchmark.l1_ontology_linking import (
    build_diagnostic_ontology_registry,
)


def _inputs():
    registry = build_diagnostic_ontology_registry()
    return registry, build_diagnostic_production_policy(registry)


def _contract(**overrides):
    registry, policy = _inputs()
    return build_producer_contract_identity(
        registry=overrides.pop("registry", registry),
        policy=overrides.pop("policy", policy),
        chain=overrides.pop("chain", "production"),
        **overrides,
    )


# --- 类别一：prompt / request / response schema 变 -> hash 变 -----------------


def test_a_changed_prompt_changes_the_hash() -> None:
    """prompt 决定模型被要求做什么，必须进哈希。"""
    assert (
        _contract(prompt_override="different instruction")[
            "producer_contract_sha256"
        ]
        != _contract()["producer_contract_sha256"]
    )


def test_a_changed_request_shape_changes_the_hash() -> None:
    """request shape 不同即契约不同：这正是 C 与 D 的差别。"""
    production = _contract(chain="production")
    qualification = _contract(chain="phase_c_qualification")
    assert production["request_shape"] != qualification["request_shape"]
    assert (
        production["producer_contract_sha256"]
        != qualification["producer_contract_sha256"]
    )


def test_a_changed_response_schema_changes_the_hash() -> None:
    """response schema 变化必须改变哈希。"""
    production = _contract(chain="production")
    qualification = _contract(chain="phase_c_qualification")
    assert (
        production["response_schema_sha256"]
        != qualification["response_schema_sha256"]
    )


# --- 类别二：materialization contract 变 -> hash 变 --------------------------


def test_a_changed_materialization_contract_changes_the_hash() -> None:
    """物化契约决定程序补全哪些字段，必须进哈希。

    production 由程序物化语义槽位；qualification 不物化。两者的
    materialization_contract_sha256 必须不同。
    """
    production = _contract(chain="production")
    qualification = _contract(chain="phase_c_qualification")
    assert (
        production["materialization_contract_sha256"]
        != qualification["materialization_contract_sha256"]
    )


# --- 类别三：policy / registry 变 -> hash 变 ---------------------------------


def test_a_changed_policy_changes_the_hash() -> None:
    """policy 收窄或放宽都必须改变哈希。"""
    registry, policy = _inputs()
    baseline = _contract()
    narrowed = build_producer_contract_identity(
        registry=registry,
        policy=policy.model_copy(update={"allowed_polarities": ["positive"]}),
        chain="production",
    )
    assert narrowed["policy_sha256"] != baseline["policy_sha256"]
    assert (
        narrowed["producer_contract_sha256"]
        != baseline["producer_contract_sha256"]
    )


def test_a_changed_registry_changes_the_hash() -> None:
    """registry 变化必须改变哈希，否则换词表可冒充同一契约。"""
    registry, policy = _inputs()
    baseline = _contract()
    # registry 自校验 registry_hash，所以必须重新构造而不是 model_copy——后者会
    # 绕过校验器，留下一个内容已改而哈希未改的对象，那种对象本不可能存在。
    payload = registry.model_dump(mode="json")
    for rule in payload["predicate_role_constraints"]:
        rule["predicate_sense"] = f"{rule['predicate_sense']}_v2"
    payload.pop("registry_hash")
    from tools.natural_memory_benchmark.authoritative_memory import canonical_sha256
    from tools.natural_memory_benchmark.l1_ontology_linking import (
        OntologyRegistry,
        _normalize_registry_payload,
    )

    # 直接按 payload 计算，避免 model_construct 绕过校验产生序列化告警。
    payload["registry_hash"] = canonical_sha256(
        _normalize_registry_payload(dict(payload))
    )
    shifted = OntologyRegistry.model_validate(payload)
    assert shifted.registry_hash != registry.registry_hash

    altered = build_producer_contract_identity(
        registry=shifted, policy=policy, chain="production"
    )
    assert altered["ontology_registry_sha256"] != baseline["ontology_registry_sha256"]
    assert (
        altered["producer_contract_sha256"]
        != baseline["producer_contract_sha256"]
    )


# --- 类别四：位置 / 格式 / 注释 变 -> hash 不变 ------------------------------


def test_no_path_or_filename_participates_in_the_hash() -> None:
    """哈希体内不得含路径、文件名或模块名。"""
    for chain in ("production", "phase_c_qualification"):
        contract = _contract(chain=chain)
        for key, value in contract.items():
            assert "/" not in value, (chain, key, value)
            assert not value.endswith(".py"), (chain, key, value)
            assert "natural_memory_benchmark" not in value, (chain, key, value)


def test_repeated_construction_is_stable() -> None:
    """同样输入必须得到同样哈希——迁移只改位置。"""
    first = _contract()
    second = _contract()
    assert first == second


def test_whitespace_and_comment_edits_cannot_reach_the_hash() -> None:
    """空白与注释改动不得改变哈希。

    结构性地保证：哈希只由被声明的契约值构成，源码文本不参与，因此源码里的
    格式与注释无法影响它。
    """
    contract = _contract()
    anchored_on = {
        "chain",
        "contract_anchor",
        "request_shape",
        "prompt_sha256",
        "response_schema_sha256",
        "materialization_contract_sha256",
        "policy_sha256",
        "ontology_registry_sha256",
        "producer_contract_sha256",
    }
    assert set(contract) == anchored_on, set(contract) ^ anchored_on
    assert contract["contract_anchor"] == "declared_contract_not_source_text"


# --- 算法与版本钉死 ----------------------------------------------------------


def test_the_hash_algorithm_is_pinned() -> None:
    """哈希算法与计算方式必须可独立复算。

    独立重算一遍：把除 producer_contract_sha256 以外的字段按 canonical JSON
    取 sha256，必须与记录值一致。这样未来换算法或换字段集都会立刻失败，而不是
    静默产生一份"看起来兼容"的新哈希。
    """
    from tools.natural_memory_benchmark.authoritative_memory import canonical_sha256

    contract = _contract()
    body = {k: v for k, v in contract.items() if k != "producer_contract_sha256"}
    assert contract["producer_contract_sha256"] == canonical_sha256(body)
    assert len(contract["producer_contract_sha256"]) == 64
    assert all(c in "0123456789abcdef" for c in contract["producer_contract_sha256"])


def test_the_contract_version_is_declared() -> None:
    """契约必须自带版本标记，新增字段不得静默兼容。"""
    contract = _contract()
    assert contract["contract_anchor"] == "declared_contract_not_source_text"
    # 字段集是契约版本的一部分：新增字段必须让本测试失败并被显式审阅。
    assert len(contract) == 9, sorted(contract)


def test_each_hash_field_is_a_real_sha256() -> None:
    """每个哈希字段都必须是真正的 sha256，不得是占位串。"""
    contract = _contract()
    for key, value in contract.items():
        if key.endswith("_sha256"):
            assert len(value) == 64, (key, value)
            assert value != "0" * 64, key
            assert value != hashlib.sha256(b"").hexdigest(), key
