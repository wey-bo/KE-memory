import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from typer.core import TyperGroup
from typer.main import get_command
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
    commands = (
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
    )
    for command in commands:
        assert command in result.stdout
    root_command = get_command(app)
    assert isinstance(root_command, TyperGroup)
    assert set(root_command.commands) == set(commands)


def test_cli_lists_evaluation_commands() -> None:
    from ke_memory_demo.cli import app

    result = runner.invoke(app, ["evaluate", "--help"])

    assert result.exit_code == 0
    for command in ("preflight", "smoke", "run", "report"):
        assert command in result.stdout


def test_cli_normalizes_direct_config_directory_before_core_preflight(
    monkeypatch: pytest.MonkeyPatch,
    project_root: Path,
    tmp_path: Path,
) -> None:
    import ke_memory_demo.cli as cli
    from ke_memory_demo.settings import ConfigLayout

    config_layouts: list[Path | ConfigLayout] = []

    def ontology_identity(*, mode: str) -> dict[str, str]:
        return {"mode": mode}

    class FakePipeline:
        async def preflight(self) -> SimpleNamespace:
            return SimpleNamespace(
                run_id="run-1",
                session_count=13,
                exchange_count=385,
                question_count=60,
                normalization_mode="ontology-bound",
                ontology_identity=SimpleNamespace(model_dump=ontology_identity),
            )

    class FakeFactory:
        def build_pipeline(self, _run_id: str) -> FakePipeline:
            return FakePipeline()

        async def aclose(self) -> None:
            return None

    def fake_from_paths(config_root: Path | ConfigLayout, _state_root: Path) -> FakeFactory:
        config_layouts.append(config_root)
        return FakeFactory()

    monkeypatch.setattr(cli.RuntimeFactory, "from_paths", fake_from_paths)
    result = runner.invoke(
        cli.app,
        [
            "preflight",
            "--run-id",
            "run-1",
            "--config-root",
            str(project_root / "config"),
            "--state-root",
            str(tmp_path / "state"),
        ],
    )

    assert result.exit_code == 0
    assert config_layouts == [
        ConfigLayout(
            project_root=project_root.resolve(),
            config_dir=(project_root / "config").resolve(),
        )
    ]


def test_evaluation_report_materializes_only_a_verified_canonical_snapshot(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import ke_memory_demo.cli as cli

    calls: list[tuple[Path, str, str]] = []

    def fake_materialize(state_root: Path, run_id: str, snapshot_id: str) -> tuple[Path, ...]:
        calls.append((state_root, run_id, snapshot_id))
        output = state_root / "exports" / run_id
        return tuple(
            output / name for name in ("metrics.json", "question_results.csv", "report.md")
        )

    monkeypatch.setattr(cli, "materialize_evaluation_report", fake_materialize)
    state_root = tmp_path / "state"
    result = runner.invoke(
        cli.app,
        [
            "evaluate",
            "report",
            "--run-id",
            "run-1",
            "--snapshot-id",
            "a" * 40,
            "--state-root",
            str(state_root),
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["snapshot_id"] == "a" * 40
    assert payload["counts"] == {"documents": 3}
    assert calls == [(state_root, "run-1", "a" * 40)]


@pytest.mark.parametrize(
    (
        "command",
        "answer_count",
        "formal",
        "provided_snapshot",
        "resolved_snapshot",
        "evaluation_snapshot",
    ),
    [
        ("smoke", 1, False, None, "e" * 40, None),
        ("run", 60, True, "d" * 40, "d" * 40, "f" * 40),
    ],
)
def test_evaluation_commands_run_fake_ke_only_evaluation(
    monkeypatch: pytest.MonkeyPatch,
    command: str,
    answer_count: int,
    formal: bool,
    provided_snapshot: str | None,
    resolved_snapshot: str,
    evaluation_snapshot: str | None,
) -> None:
    import ke_memory_demo.cli as cli
    from ke_memory_demo.evaluation import EvaluationStatus

    calls: list[tuple[str, str | None, bool]] = []

    # The CLI is now a composition root: it builds the pipeline factory and the
    # evaluation stage separately, so both are faked. run_evaluation lives on the
    # stage; the factory only supplies the collaborators the stage is given.
    class FakeFactory:
        settings = SimpleNamespace()
        artifacts = SimpleNamespace(root=Path("/nonexistent-state-root"))
        snapshots = SimpleNamespace()
        ontology = SimpleNamespace()
        work_model = SimpleNamespace()
        code_commit = "b" * 40

        async def aclose(self) -> None:
            return None

    class FakeStage:
        evaluation_snapshot_id: str | None = None

        async def run_evaluation(
            self,
            run_id: str,
            snapshot_id: str | None,
            *,
            smoke: bool,
        ) -> SimpleNamespace:
            calls.append((run_id, snapshot_id, smoke))
            self.evaluation_snapshot_id = evaluation_snapshot
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

    def fake_from_paths(
        _config_root: Path,
        _state_root: Path,
        **_kwargs: object,
    ) -> FakeFactory:
        return FakeFactory()

    monkeypatch.setattr(cli.RuntimeFactory, "from_paths", fake_from_paths)
    monkeypatch.setattr(cli, "EvaluationStage", lambda **_kwargs: FakeStage())
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
    assert payload["evaluation_snapshot_id"] == evaluation_snapshot
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


def test_evaluation_preflight_collects_invalid_layout_without_ingestion(
    tmp_path: Path,
) -> None:
    import ke_memory_demo.cli as cli
    from ke_memory_demo.evaluation.preflight import PREFLIGHT_CHECK_NAMES

    config_root = tmp_path / "invalid-config-root"
    config_root.mkdir()
    state_root = tmp_path / "state"

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
            str(config_root),
            "--state-root",
            str(state_root),
        ],
    )

    assert result.exit_code == 2
    payload = json.loads(result.stdout)
    assert payload["ready"] is False
    assert [item["name"] for item in payload["checks"]] == sorted(PREFLIGHT_CHECK_NAMES)
    assert all(item["passed"] is False for item in payload["checks"])
    details = {item["name"]: item["detail"] for item in payload["checks"]}
    for name in (
        "concurrency",
        "embedding",
        "environment",
        "judge_model",
        "ontology_identity",
        "work_model",
    ):
        assert details[name] == f"{name}:SettingsError"
    assert result.stdout.strip() == json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    assert result.stderr == ""
    assert not state_root.exists()


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
