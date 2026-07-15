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
