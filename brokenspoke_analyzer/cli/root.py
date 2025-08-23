"""Define the top-level commands."""

import logging
import typing
from importlib import (
    metadata,
)

import typer
from loguru import logger
from rich.logging import RichHandler
from typing_extensions import Annotated

from brokenspoke_analyzer.cli import (
    cache,
    common,
    compute,
    configure,
    export,
    importer,
    prepare,
    run,
    run_with,
)

# Create the CLI app.
app = typer.Typer()
verbose = False


def _verbose_callback(value: int) -> None:
    """Configure the logger."""
    # Remove any predefined logger.
    logger.remove()

    # The log level gets adjusted by adding/removing `-v` flags:
    #   None    : Initial log level is WARNING.
    #   -v      : INFO
    #   -vv     : DEBUG
    #   -vvv    : TRACE
    initial_log_level = logging.WARNING
    log_level = max(initial_log_level - value * 10, 0)

    # Add the logger.
    logger.add(
        RichHandler(
            markup=True,
            rich_tracebacks=True,
            tracebacks_show_locals=True,
            log_time_format="[%X]",
        ),
        format="{message}",
        level=log_level,
        colorize=True,
    )

    verbose = value > 0


def _version_callback(value: bool) -> None:
    """Get the package's version."""
    package_version = metadata.version("brokenspoke-analyzer")
    if value:
        typer.echo(f"brokenspoke-analyzer version: {package_version}")
        raise typer.Exit()


@app.callback()
def callback(
    version: Annotated[
        typing.Optional[bool],
        typer.Option(
            "--version",
            help="Show the application's version and exit.",
            callback=_version_callback,
        ),
    ] = None,
    verbose: Annotated[
        typing.Optional[int],
        typer.Option(
            "--verbose",
            "-v",
            help="Set logger's verbosity.",
            count=True,
            callback=_verbose_callback,
        ),
    ] = 0,
) -> None:
    """Define callback to configure global flags."""
    return


# Register the sub-commands.
app.add_typer(cache.app, name="cache", help="Manage bna's cache.")
app.add_typer(compute.app, help="Compute the analysis results.")
app.add_typer(
    configure.app, name="configure", help="Configure a database for an analysis."
)
app.add_typer(export.app, name="export", help="Export tables from database.")
app.add_typer(importer.app, name="import", help="Import files into database.")
app.add_typer(prepare.app, help="Prepare files needed for an analysis.")
app.add_typer(run.app, help="Run a full analysis.")
app.add_typer(run_with.app, name="run-with", help="Run an analysis in different ways.")

# Make shared options accessible to appropriate subcommands.
run_with.verbose = verbose
