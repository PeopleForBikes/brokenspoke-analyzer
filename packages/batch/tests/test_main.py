"""Test the main module."""

import typer

from bna.batch import main


def test_command_exposes_the_options() -> None:
    """Ensure the command exposes the batch file and every option."""
    app = typer.Typer()
    app.command()(main.main)
    command = typer.main.get_command(app)
    names = {opt for param in command.params for opt in param.opts}
    assert {
        "batch_file",
        "--export-dir",
        "--lodes-year",
        "--with-parts",
        "--worldpop-year",
    } <= names
