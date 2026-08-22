"""Test the root module."""

from typer.testing import CliRunner

from brokenspoke_analyzer_cli import root

runner = CliRunner()


def test_help_lists_the_subcommands() -> None:
    """Ensure the top level help advertises every pipeline stage."""
    result = runner.invoke(root.app, ["--help"])
    assert result.exit_code == 0
    for subcommand in [
        "cache",
        "compute",
        "configure",
        "export",
        "import",
        "prepare",
        "run",
        "run-with",
    ]:
        assert subcommand in result.output
