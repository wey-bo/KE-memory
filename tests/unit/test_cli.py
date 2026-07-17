import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from typer.testing import CliRunner


runner = CliRunner()


def test_cli_root_help_is_available():
    from ke_memory_demo.cli import app

    result = runner.invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "KE memory research demo" in result.stdout
    assert "--version" in result.stdout


def test_cli_root_version_is_available():
    from ke_memory_demo.cli import app

    result = runner.invoke(app, ["--version"])

    assert result.exit_code == 0
    assert result.stdout.strip() == "ke-memory 0.1.0"


def test_cli_lists_ke_only_stages() -> None:
    from ke_memory_demo.cli import app

    result = runner.invoke(app, ["--help"])

    assert result.exit_code == 0
    for command in (
        "preflight",
        "ingest",
        "extract-turn-ke",
        "aggregate-session",
        "build-semantic-dag",
        "prepare-ke",
        "run-pipeline",
        "retrieve",
        "verify-snapshot",
        "evaluate",
    ):
        assert command in result.stdout
    assert "run-baselines" not in result.stdout


def test_cli_lists_evaluation_commands() -> None:
    from ke_memory_demo.cli import app

    result = runner.invoke(app, ["evaluate", "--help"])

    assert result.exit_code == 0
    for command in ("preflight", "smoke", "run"):
        assert command in result.stdout


@pytest.mark.parametrize(
    ("command", "answer_count", "formal", "provided_snapshot", "resolved_snapshot"),
    [
        ("smoke", 1, False, None, "e" * 40),
        ("run", 60, True, "d" * 40, "d" * 40),
    ],
)
def test_evaluation_commands_run_fake_ke_only_evaluation(
    monkeypatch: pytest.MonkeyPatch,
    command: str,
    answer_count: int,
    formal: bool,
    provided_snapshot: str | None,
    resolved_snapshot: str,
) -> None:
    import ke_memory_demo.cli as cli
    from ke_memory_demo.evaluation import EvaluationStatus

    calls: list[tuple[str, str | None, bool]] = []

    class FakeFactory:
        async def run_evaluation(
            self,
            run_id: str,
            snapshot_id: str | None,
            *,
            smoke: bool,
        ) -> SimpleNamespace:
            calls.append((run_id, snapshot_id, smoke))
            values = tuple(object() for _ in range(answer_count))
            return SimpleNamespace(
                manifest_hash="a" * 64,
                ke_ready_snapshot_id=resolved_snapshot,
                status=EvaluationStatus.COMPLETE,
                answers=values,
                judgements=values,
                failures=(),
            )

        async def aclose(self) -> None:
            return None

    def fake_from_paths(_config_root: Path, _state_root: Path) -> FakeFactory:
        return FakeFactory()

    monkeypatch.setattr(cli.RuntimeFactory, "from_paths", fake_from_paths)
    arguments = [
        "evaluate",
        command,
        "--run-id",
        "run-1",
        "--config-root",
        ".",
        "--state-root",
        "state",
    ]
    if provided_snapshot is not None:
        arguments.extend(("--snapshot-id", provided_snapshot))
    result = runner.invoke(cli.app, arguments)

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["mode"] == command
    assert payload["formal"] is formal
    assert payload["snapshot_id"] == resolved_snapshot
    assert payload["counts"] == {
        "answers": answer_count,
        "failures": 0,
        "judgements": answer_count,
    }
    assert calls == [("run-1", provided_snapshot, command == "smoke")]


def test_evaluation_preflight_prints_canonical_json_and_exits_two_when_not_ready(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import ke_memory_demo.cli as cli
    from ke_memory_demo.evaluation import EvaluationPreflight, PreflightCheckFailure

    class FakePorts:
        async def check(self, name: str) -> str:
            if name == "judge_model":
                raise PreflightCheckFailure("judge_model:Unavailable")
            return f"{name}:ok"

    def fake_builder(
        _config_root: Path,
        _state_root: Path,
        _run_id: str,
        _snapshot_id: str,
    ) -> EvaluationPreflight:
        return EvaluationPreflight(FakePorts())

    monkeypatch.setattr(cli, "build_evaluation_preflight", fake_builder)
    result = runner.invoke(
        cli.app,
        [
            "evaluate",
            "preflight",
            "--run-id",
            "run-1",
            "--snapshot-id",
            "a" * 40,
            "--config-root",
            ".",
            "--state-root",
            "state",
        ],
    )

    assert result.exit_code == 2
    payload = json.loads(result.stdout)
    assert payload["ready"] is False
    assert [item["name"] for item in payload["checks"] if not item["passed"]] == ["judge_model"]
    assert result.stdout.strip() == json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def test_stage_command_refuses_a_skipped_prerequisite(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import ke_memory_demo.cli as cli

    class FakePipeline:
        async def preflight(self) -> object:
            return object()

        async def extract_turn_ke(self) -> object:
            raise cli.PipelineInvariantError(
                "stage turn-ke-extracted requires completed prerequisite ingested"
            )

    class FakeFactory:
        def build_pipeline(self, _run_id: str) -> FakePipeline:
            return FakePipeline()

        async def aclose(self) -> None:
            return None

    def fake_from_paths(_config_root: Path, _state_root: Path) -> FakeFactory:
        return FakeFactory()

    monkeypatch.setattr(cli.RuntimeFactory, "from_paths", fake_from_paths)

    result = runner.invoke(
        cli.app,
        [
            "extract-turn-ke",
            "--run-id",
            "run-1",
            "--config-root",
            ".",
            "--state-root",
            "state",
        ],
    )

    assert result.exit_code != 0
    assert "requires completed prerequisite ingested" in result.stderr
