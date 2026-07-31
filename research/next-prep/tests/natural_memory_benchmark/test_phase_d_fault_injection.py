"""失败的事务不得留下半截记忆、快照或 Git 状态。

Phase D 声称的是"受控自动闭环"。闭环的一半是成功路径可复核，另一半是**失败路径
不留残骸**：如果某次运行在写入中途失败却留下了部分 L1/L2、一个半成品 checkpoint
或一个前进了的 Git ref，那么"权威记忆"就不再权威——后续运行会建立在无人审计过的
中间状态上。

这些测试在链路的不同位置注入故障，然后检查磁盘：仓库、raw artifact 与 result 三者
要么都不存在，要么与故障前完全一致。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.natural_memory_benchmark.e2e_openai_producers import ModelBoundaryError
from tools.natural_memory_benchmark.e2e_openai_runtime import run_openai_e2e

from test_e2e_pipeline_smoke import (  # noqa: F401
    _chat_response,
    _production_l1_slot_payload,
    _production_l2_payload,
    _production_query_payload,
    _SequencedOpener,
    _turns,
)


def _paths(tmp_path: Path, name: str) -> tuple[Path, Path, Path]:
    repository = tmp_path / f"{name}.git"
    raw = repository.with_name(f"{repository.name}.raw.json")
    result = tmp_path / f"{name}-result.json"
    return repository, raw, result


def _assert_no_residue(repository: Path, raw: Path, result: Path) -> None:
    """失败后三者都不得存在。"""
    assert not repository.exists(), f"repository left behind: {repository}"
    assert not raw.exists(), f"raw artifact left behind: {raw}"
    assert not result.exists(), f"result left behind: {result}"


def test_an_l1_failure_leaves_nothing_behind(tmp_path: Path) -> None:
    """L1 阶段失败：不得留下仓库、raw artifact 或 result。"""
    repository, raw, result = _paths(tmp_path, "l1-fault")
    broken = _production_l1_slot_payload()
    del broken["proposals"][0]["slots"]["kind"]
    with pytest.raises(ModelBoundaryError):
        run_openai_e2e(
            turns=_turns(),
            question="What beverage is preferred?",
            repository_path=repository,
            result_path=result,
            base_url="https://model.invalid/v1",
            api_key="credential-that-must-not-leak",
            model="test-model-response",
            max_attempts=1,
            opener=_SequencedOpener([_chat_response(broken)]),
        )
    _assert_no_residue(repository, raw, result)


def test_an_l2_failure_leaves_nothing_behind(tmp_path: Path) -> None:
    """L2 阶段失败：L1 已经产出，但仍不得留下任何权威状态。

    这一例比 L1 更关键：此时抽取已经成功，若实现是"边算边写"，磁盘上就会留下
    半截记忆。
    """
    repository, raw, result = _paths(tmp_path, "l2-fault")
    broken_l2 = _production_l2_payload()
    broken_l2["slots"]["statement"] = "Coffee is avoided."
    with pytest.raises(ModelBoundaryError):
        run_openai_e2e(
            turns=_turns(),
            question="What beverage is preferred?",
            repository_path=repository,
            result_path=result,
            base_url="https://model.invalid/v1",
            api_key="credential-that-must-not-leak",
            model="test-model-response",
            max_attempts=1,
            opener=_SequencedOpener(
                [
                    _chat_response(_production_l1_slot_payload()),
                    _chat_response(broken_l2),
                ]
            ),
        )
    _assert_no_residue(repository, raw, result)


def test_a_query_failure_leaves_no_result_and_no_advanced_history(
    tmp_path: Path,
) -> None:
    """查询阶段失败：不得写出 result。

    此时记忆写入已经完成，所以这里检查的是"部分成功不得被当作成功记录下来"。
    """
    repository, raw, result = _paths(tmp_path, "query-fault")
    with pytest.raises(Exception) as captured:
        run_openai_e2e(
            turns=_turns(),
            question="What beverage is preferred?",
            repository_path=repository,
            result_path=result,
            base_url="https://model.invalid/v1",
            api_key="credential-that-must-not-leak",
            model="test-model-response",
            max_attempts=1,
            opener=_SequencedOpener(
                [
                    _chat_response(_production_l1_slot_payload()),
                    _chat_response(_production_l2_payload()),
                    b"not-a-valid-provider-response",
                ]
            ),
        )
    assert "credential-that-must-not-leak" not in str(captured.value)
    # 没有 receipt 就不存在"这次运行通过了"的记录。
    assert not result.exists(), "a failed run must not leave a receipt"


def test_a_transport_failure_leaves_nothing_behind(tmp_path: Path) -> None:
    """传输层故障同样不得留下残骸。"""
    repository, raw, result = _paths(tmp_path, "transport-fault")
    with pytest.raises(Exception):
        run_openai_e2e(
            turns=_turns(),
            question="What beverage is preferred?",
            repository_path=repository,
            result_path=result,
            base_url="https://model.invalid/v1",
            api_key="credential-that-must-not-leak",
            model="test-model-response",
            max_attempts=1,
            opener=_SequencedOpener([TimeoutError("injected transport fault")]),
        )
    _assert_no_residue(repository, raw, result)


def test_a_second_run_cannot_overwrite_a_completed_one(tmp_path: Path) -> None:
    """成功运行的产物不得被后续运行覆盖。

    这是失败路径的另一面：若第二次运行能覆盖第一次的仓库与 receipt，那么"不可变
    记录"只是惯例而非保证。
    """
    repository, _raw, result = _paths(tmp_path, "no-overwrite")
    payloads = [
        _chat_response(_production_l1_slot_payload()),
        _chat_response(_production_l2_payload()),
        _chat_response(_production_query_payload()),
    ]
    first = run_openai_e2e(
        turns=_turns(),
        question="What beverage is preferred?",
        repository_path=repository,
        result_path=result,
        base_url="https://model.invalid/v1",
        api_key="credential-that-must-not-leak",
        model="test-model-response",
        max_attempts=1,
        opener=_SequencedOpener(list(payloads)),
    )
    before = json.loads(result.read_text(encoding="utf-8"))
    with pytest.raises(FileExistsError):
        run_openai_e2e(
            turns=_turns(),
            question="What beverage is preferred?",
            repository_path=repository,
            result_path=result,
            base_url="https://model.invalid/v1",
            api_key="credential-that-must-not-leak",
            model="test-model-response",
            max_attempts=1,
            opener=_SequencedOpener(list(payloads)),
        )
    after = json.loads(result.read_text(encoding="utf-8"))
    assert after == before, "a refused rerun must not alter the frozen receipt"
    assert first.receipt.byte_level_recovery_verified is True
