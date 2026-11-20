"""Test the root module."""

from importlib import metadata

from typer.testing import CliRunner

from bna.cli import root

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


def test_version_reports_the_cli_distribution_version() -> None:
    """Ensure ``--version`` reads the version of the ``bna-cli`` distribution."""
    result = runner.invoke(root.app, ["--version"])
    assert result.exit_code == 0
    assert metadata.version("bna-cli") in result.output


def test_subcommand_help_runs_the_root_callback() -> None:
    """Ensure a subcommand runs the root callbacks, ``--version`` included.

    The root ``--help`` exits before the option callbacks run, so it cannot
    detect a callback that fails on every invocation.
    """
    result = runner.invoke(root.app, ["cache", "--help"])
    assert result.exit_code == 0, result.output
