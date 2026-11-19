"""Test the main module."""

import typer
from typer.testing import CliRunner

from brokenspoke_analyzer_batch import main

runner = CliRunner()


def test_help_lists_the_options() -> None:
    """Ensure the help advertises the batch file and every option."""
    app = typer.Typer()
    app.command()(main.main)
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    for option in [
        "batch_file",
        "--export-dir",
        "--lodes-year",
        "--with-parts",
        "--worldpop-year",
    ]:
        assert option in result.output
