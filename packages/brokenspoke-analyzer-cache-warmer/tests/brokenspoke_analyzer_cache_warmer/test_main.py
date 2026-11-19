"""Test the main module."""

from typer.testing import CliRunner

from brokenspoke_analyzer_cache_warmer import main

runner = CliRunner()


def test_help_lists_the_subcommands() -> None:
    """Ensure the help advertises every cache target."""
    result = runner.invoke(main.app, ["--help"])
    assert result.exit_code == 0
    for subcommand in ["local", "s3"]:
        assert subcommand in result.output
