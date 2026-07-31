"""runner 的机制必须在花掉那一次 attempt 之前验证。

每层只有一次真实请求，所以冻结顺序、拒绝覆盖、凭据安全这些必须先用替身确认。
真实调用出错时才发现 runner 自己写错了，那一次 attempt 就白费了，而按预注册不
允许重试同一 attempt。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.natural_memory_benchmark import operational_profile_fresh_runner as runner

CREDENTIAL = "credential-that-must-not-reach-any-artifact"


@pytest.fixture(scope="module")
def dataset(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A dataset built under the corrected contract.

    The frozen v1 dataset carries the drifted vocabulary that broke attempt 1,
    and it must not be edited in place, so the runner's mechanics are exercised
    against a freshly materialized dataset instead. The guard refusing v1 is the
    fix working, not a problem to route around.
    """
    from tools.natural_memory_benchmark.operational_profile_fresh_materialization import (
        freeze_dataset,
    )

    root = tmp_path_factory.mktemp("contract-bound-dataset") / "dataset"
    freeze_dataset(root)
    return root


def _stub_response(payload: dict[str, object]) -> bytes:
    return json.dumps(
        {
            "model": "stub-model-response",
            "choices": [{"message": {"content": json.dumps(payload)}}],
        },
        sort_keys=True,
    ).encode("utf-8")


@pytest.fixture()
def stub_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_BASE_URL", "https://model.invalid/v1")
    monkeypatch.setenv("OPENAI_API_KEY", CREDENTIAL)
    monkeypatch.setenv("OPENAI_MODEL", "stub-model-response")


def _patch_request(monkeypatch: pytest.MonkeyPatch, response: bytes) -> list[dict]:
    calls: list[dict] = []

    def fake_request(**kwargs: object) -> bytes:
        calls.append(dict(kwargs))
        return response

    monkeypatch.setattr(runner, "_request", fake_request)
    return calls


def test_freeze_order_and_read_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, stub_env: None, dataset: Path
) -> None:
    """四个产物必须按 dispatch→raw→proposals→provenance 冻结且只读。"""
    public = json.loads((dataset / "public-l1.json").read_text())
    proposals = {
        "proposals": [
            {
                "case_id": case["case_id"],
                "candidate_ref": case["candidate_ref"],
                "decision": "no_memory",
                "confidence": 0.5,
                "reason_code": "stub",
                "typed_candidate": None,
            }
            for case in public["cases"]
        ]
    }
    _patch_request(monkeypatch, _stub_response(proposals))
    attempt = tmp_path / "attempt"
    result = runner.run_layer(
        layer="l1", dataset_root=dataset, attempt_root=attempt
    )

    names = [
        "dispatch-l1.json",
        "raw-response-l1.json",
        "proposals-l1.json",
        "provenance-l1.json",
    ]
    for name in names:
        path = attempt / name
        assert path.is_file(), name
        assert path.stat().st_mode & 0o222 == 0, name

    provenance = json.loads((attempt / "provenance-l1.json").read_text())
    assert provenance["freeze_sequence"] == [
        "dispatch",
        "raw_response",
        "proposals",
        "provenance",
    ]
    # provenance 必须绑定前三者的实际哈希。
    assert provenance["dispatch_sha256"] == result["dispatch_sha256"]
    assert provenance["raw_response_sha256"] == result["raw_response_sha256"]
    assert provenance["proposals_sha256"] == result["proposals_sha256"]
    assert provenance["authority_or_gold_read_before_freeze"] is False
    assert provenance["requests_issued"] == 1
    assert provenance["retried"] is False


def test_exactly_one_request_is_issued(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, stub_env: None, dataset: Path
) -> None:
    """一层只能发出一次请求。"""
    public = json.loads((dataset / "public-l1.json").read_text())
    calls = _patch_request(
        monkeypatch,
        _stub_response(
            {
                "proposals": [
                    {
                        "case_id": case["case_id"],
                        "candidate_ref": case["candidate_ref"],
                        "decision": "abstain",
                        "confidence": 0.4,
                        "reason_code": "stub",
                        "typed_candidate": None,
                    }
                    for case in public["cases"]
                ]
            }
        ),
    )
    runner.run_layer(
        layer="l1", dataset_root=dataset, attempt_root=tmp_path / "one"
    )
    assert len(calls) == 1


def test_no_artifact_contains_the_credential(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, stub_env: None, dataset: Path
) -> None:
    """凭据不得出现在任何冻结产物里。"""
    public = json.loads((dataset / "public-l1.json").read_text())
    _patch_request(
        monkeypatch,
        _stub_response(
            {
                "proposals": [
                    {
                        "case_id": case["case_id"],
                        "candidate_ref": case["candidate_ref"],
                        "decision": "no_memory",
                        "confidence": 0.5,
                        "reason_code": "stub",
                        "typed_candidate": None,
                    }
                    for case in public["cases"]
                ]
            }
        ),
    )
    attempt = tmp_path / "credential-check"
    runner.run_layer(layer="l1", dataset_root=dataset, attempt_root=attempt)
    for path in attempt.iterdir():
        assert CREDENTIAL not in path.read_text(encoding="utf-8"), path.name


def test_a_populated_attempt_root_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, stub_env: None, dataset: Path
) -> None:
    """已有内容的 attempt 目录必须被拒绝：冻结记录不得被改写。"""
    attempt = tmp_path / "used"
    attempt.mkdir()
    (attempt / "leftover.json").write_text("{}", encoding="utf-8")
    with pytest.raises(runner.ProposerError, match="already populated"):
        runner.run_layer(
            layer="l1", dataset_root=dataset, attempt_root=attempt
        )


def test_missing_configuration_fails_before_any_request(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, dataset: Path
) -> None:
    """配置缺失必须在发请求之前失败，且不得泄漏值。"""
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("OPENAI_BASE_URL", "https://model.invalid/v1")
    monkeypatch.setenv("OPENAI_MODEL", "stub-model-response")
    calls = _patch_request(monkeypatch, b"{}")
    with pytest.raises(runner.ProposerError, match="OPENAI_API_KEY"):
        runner.run_layer(
            layer="l1", dataset_root=dataset, attempt_root=tmp_path / "nocfg"
        )
    assert calls == []


def test_non_json_content_fails_with_a_fingerprint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, stub_env: None, dataset: Path
) -> None:
    """非 JSON 响应必须以指纹报错，而不是回显内容。"""
    _patch_request(
        monkeypatch,
        json.dumps(
            {
                "model": "stub-model-response",
                "choices": [{"message": {"content": "sensitive-provider-text"}}],
            }
        ).encode("utf-8"),
    )
    with pytest.raises(runner.ProposerError) as captured:
        runner.run_layer(
            layer="l1", dataset_root=dataset, attempt_root=tmp_path / "bad"
        )
    message = str(captured.value)
    assert "response_sha256=" in message
    assert "sensitive-provider-text" not in message


def test_gold_exposure_is_checked_before_the_request(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, stub_env: None, dataset: Path
) -> None:
    """gold 可达时必须在发请求之前就失败。"""
    calls = _patch_request(monkeypatch, b"{}")

    def leaking_check(**kwargs: object) -> None:
        raise ValueError("gold artifact lies inside a proposer-readable directory")

    monkeypatch.setattr(
        "tools.natural_memory_benchmark.operational_profile_fresh_prereg"
        ".assert_gold_not_exposed",
        leaking_check,
    )
    with pytest.raises(ValueError, match="gold"):
        runner.run_layer(
            layer="l1", dataset_root=dataset, attempt_root=tmp_path / "leak"
        )
    assert calls == []
