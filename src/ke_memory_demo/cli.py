from importlib.metadata import version as package_version
from typing import Annotated

import typer


app = typer.Typer(
    add_completion=False,
    help="KE memory research demo.",
    no_args_is_help=True,
)


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"ke-memory {package_version('ke-memory-demo')}")
        raise typer.Exit()


@app.callback(invoke_without_command=True)
def main(
    version: Annotated[
        bool,
        typer.Option(
            "--version",
            callback=_version_callback,
            help="Show the version and exit.",
            is_eager=True,
        ),
    ] = False,
) -> None:
    """Run the KE memory research demo."""
