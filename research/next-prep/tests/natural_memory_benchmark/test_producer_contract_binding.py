"""profile hash 相同不代表 producer contract 相同。

审计的 Critical 项：Phase C 的 runner 要求模型返回完整 typed_candidate，Phase D
的 production 路径要求 `production-l1-slot-batch-response-v1` 语义槽位并由程序补
全其余字段；Phase D attempt 1 之后我还改了 predicate prompt。而 closure 只比对了
`profile_sha256=80a2f472`——那个哈希覆盖词表、registry 与 policy，**不覆盖 prompt、
response schema、producer 与 materializer**。

于是"Phase C 资格适用于 Phase D producer"无法从现有证据推出。这里加一个覆盖这些
维度的 `producer_contract_sha256`，把差异变成可检测的事实，而不是继续用 profile
哈希代替它。
"""

from __future__ import annotations

import pytest

from tools.natural_memory_benchmark.e2e_openai_producers import (
    build_diagnostic_production_policy,
)
from tools.natural_memory_benchmark.l1_ontology_linking import (
    build_diagnostic_ontology_registry,
)


def _inputs():
    registry = build_diagnostic_ontology_registry()
    return registry, build_diagnostic_production_policy(registry)


def test_the_contract_covers_more_than_the_profile() -> None:
    """契约哈希必须覆盖 prompt、schema、producer、materializer、policy、registry。"""
    from tools.natural_memory_benchmark.e2e_openai_producers import (
        build_producer_contract_identity,
    )

    registry, policy = _inputs()
    contract = build_producer_contract_identity(
        registry=registry, policy=policy, chain="production"
    )
    # 锚点是被声明的契约，不是实现它的源码文本：源码哈希会随迁移改变，而模型
    # 被要求做什么并没有改变。
    for name in (
        "chain",
        "contract_anchor",
        "request_shape",
        "prompt_sha256",
        "response_schema_sha256",
        "materialization_contract_sha256",
        "policy_sha256",
        "ontology_registry_sha256",
        "producer_contract_sha256",
    ):
        assert name in contract, name


def test_the_two_chains_have_different_contracts() -> None:
    """Phase C 与 Phase D 的契约哈希必须不同——这正是审计指出的事实。

    两者 profile hash 相同，contract hash 不同，所以资格不能直接迁移。
    """
    from tools.natural_memory_benchmark.e2e_openai_producers import (
        build_producer_contract_identity,
    )

    registry, policy = _inputs()
    production = build_producer_contract_identity(
        registry=registry, policy=policy, chain="production"
    )
    qualification = build_producer_contract_identity(
        registry=registry, policy=policy, chain="phase_c_qualification"
    )
    assert production["policy_sha256"] == qualification["policy_sha256"]
    assert production["ontology_registry_sha256"] == (
        qualification["ontology_registry_sha256"]
    )
    # 同一 profile，不同 contract。
    assert production["prompt_sha256"] != qualification["prompt_sha256"]
    assert production["response_schema_sha256"] != (
        qualification["response_schema_sha256"]
    )
    assert production["producer_contract_sha256"] != (
        qualification["producer_contract_sha256"]
    )


def test_a_contract_mismatch_refuses_qualification_transfer() -> None:
    """契约不一致时必须拒绝资格迁移，而不是只看 profile。"""
    from tools.natural_memory_benchmark.e2e_openai_producers import (
        assert_producer_contract_transferable,
        build_producer_contract_identity,
    )

    registry, policy = _inputs()
    production = build_producer_contract_identity(
        registry=registry, policy=policy, chain="production"
    )
    qualification = build_producer_contract_identity(
        registry=registry, policy=policy, chain="phase_c_qualification"
    )
    assert_producer_contract_transferable(
        qualified_contract=production, execution_contract=production
    )
    with pytest.raises(ValueError, match="producer contract"):
        assert_producer_contract_transferable(
            qualified_contract=qualification, execution_contract=production
        )


def test_changing_the_prompt_changes_the_contract() -> None:
    """prompt 变化必须改变契约哈希，否则改 prompt 仍可冒充同一契约。"""
    from tools.natural_memory_benchmark.e2e_openai_producers import (
        build_producer_contract_identity,
    )

    registry, policy = _inputs()
    baseline = build_producer_contract_identity(
        registry=registry, policy=policy, chain="production"
    )
    altered = build_producer_contract_identity(
        registry=registry,
        policy=policy,
        chain="production",
        prompt_override="a different prompt",
    )
    assert altered["prompt_sha256"] != baseline["prompt_sha256"]
    assert altered["producer_contract_sha256"] != (
        baseline["producer_contract_sha256"]
    )
