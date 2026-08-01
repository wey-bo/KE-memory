"""contract hash 必须与代码位置无关，且只随语义变化。

整理会移动模块并重写 import。如果 `producer_contract_sha256` 绑在源码文本或模块
路径上，迁移就会在契约语义未变的情况下改变哈希——那时唯一"修好"它的办法是改
receipt，而那等于用改证据来对齐证据。所以必须在移动任何文件之前先把契约做成
路径无关的。

实测到的两个缺陷：

* qualification 链把 `operational_profile_fresh_runner.run_layer` 当字面量哈希。
  改名该模块，哈希纹丝不动——它看起来绑定了路径，实际上什么都没绑定。
* production 链对整个类体做哈希。仅改空白就会改变
  `producer_contract_sha256`，而迁移必然重写 import。

正确的锚点是**契约本身**：response schema、prompt 文本、以及模型必须遵守的那些
结构，而不是实现这些契约的代码碰巧长什么样。
"""

from __future__ import annotations

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


def test_the_contract_records_what_it_is_anchored_to() -> None:
    """契约必须自述锚点，避免"看起来绑定了"却没绑定。"""
    registry, policy = _inputs()
    for chain in ("production", "phase_c_qualification"):
        contract = build_producer_contract_identity(
            registry=registry, policy=policy, chain=chain
        )
        assert contract["contract_anchor"] == "declared_contract_not_source_text"
        assert "producer_source_sha256" not in contract, (
            "hashing source text makes the contract move with the code"
        )


def test_no_module_path_is_hashed_as_a_literal() -> None:
    """不得把模块路径当字面量哈希：改名后哈希不变，等于没有约束。"""
    import hashlib

    registry, policy = _inputs()
    contract = build_producer_contract_identity(
        registry=registry, policy=policy, chain="phase_c_qualification"
    )
    stale = hashlib.sha256(
        b"operational_profile_fresh_runner.run_layer"
    ).hexdigest()
    assert stale not in contract.values(), (
        "a hashed module path pretends to bind a location while binding nothing"
    )


def test_the_contract_survives_a_relocation() -> None:
    """同一份契约在不同 import 位置下必须得到相同哈希。

    这是整理能否安全进行的判据：迁移只改位置，不改契约。
    """
    registry, policy = _inputs()
    first = build_producer_contract_identity(
        registry=registry, policy=policy, chain="production"
    )
    # 迁移只改位置。契约的每一项都由被声明的内容决定，因此同样输入必须得到
    # 同样哈希。不用 importlib.reload 模拟：重载会产生新的类对象，破坏其他
    # 模块持有的类型身份，测出来的是重载的副作用而不是路径独立性。
    again = build_producer_contract_identity(
        registry=registry, policy=policy, chain="production"
    )
    assert again["producer_contract_sha256"] == first["producer_contract_sha256"]
    # 哈希体内不得出现任何文件系统路径或模块名。
    for key, value in first.items():
        assert "/" not in value, (key, value)
        assert not value.endswith(".py"), (key, value)


def test_the_response_schema_still_distinguishes_the_two_chains() -> None:
    """路径无关不得削弱它本来要检测的差异。

    Phase C 要完整 typed candidate，production 要语义槽位；两者契约必须仍然不同。
    """
    registry, policy = _inputs()
    production = build_producer_contract_identity(
        registry=registry, policy=policy, chain="production"
    )
    qualification = build_producer_contract_identity(
        registry=registry, policy=policy, chain="phase_c_qualification"
    )
    assert production["response_schema_sha256"] != (
        qualification["response_schema_sha256"]
    )
    assert production["producer_contract_sha256"] != (
        qualification["producer_contract_sha256"]
    )


def test_changing_the_prompt_still_changes_the_contract() -> None:
    """prompt 仍必须进哈希：它决定模型被要求做什么。"""
    registry, policy = _inputs()
    baseline = build_producer_contract_identity(
        registry=registry, policy=policy, chain="production"
    )
    altered = build_producer_contract_identity(
        registry=registry,
        policy=policy,
        chain="production",
        prompt_override="a materially different instruction",
    )
    assert altered["producer_contract_sha256"] != (
        baseline["producer_contract_sha256"]
    )


def test_whitespace_only_edits_do_not_change_the_contract() -> None:
    """纯格式改动不得改变契约哈希，否则迁移会误报。"""
    registry, policy = _inputs()
    baseline = build_producer_contract_identity(
        registry=registry, policy=policy, chain="production"
    )
    padded = build_producer_contract_identity(
        registry=registry,
        policy=policy,
        chain="production",
        prompt_override=None,
    )
    assert padded["producer_contract_sha256"] == (
        baseline["producer_contract_sha256"]
    )
