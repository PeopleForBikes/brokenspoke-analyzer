import asyncio
import logging
import pathlib
import sys
import typing

import typer
from loguru import logger
from rich.console import Console

from brokenspoke_analyzer.cli import (
    common,
    configure,
    export,
    importer,
    prepare,
)
from brokenspoke_analyzer.core import (
    analysis,
    runner,
)


def callback(verbose: int = typer.Option(0, "--verbose", "-v", count=True)) -> None:
    """Define callback to configure global flags."""
    # Configure the logger.

    # Remove any predefined logger.
    logger.remove()

    # The log level gets adjusted by adding/removing `-v` flags:
    #   None    : Initial log level is WARNING.
    #   -v      : INFO
    #   -vv     : DEBUG
    #   -vvv    : TRACE
    initial_log_level = logging.WARNING
    log_format = (
        "<level>{time:YYYY-MM-DDTHH:mm:ssZZ} {level:.3} {name}:{line} {message}</level>"
    )
    log_level = max(initial_log_level - verbose * 10, 0)

    # Set the log colors.
    logger.level("ERROR", color="<red><bold>")
    logger.level("WARNING", color="<yellow>")
    logger.level("SUCCESS", color="<green>")
    logger.level("INFO", color="<cyan>")
    logger.level("DEBUG", color="<blue>")
    logger.level("TRACE", color="<magenta>")

    # Add the logger.
    logger.add(sys.stdout, format=log_format, level=log_level, colorize=True)


# Create the CLI app.
app = typer.Typer()
app.add_typer(
    configure.app, name="configure", help="Configure a database for an analysis."
)
app.add_typer(prepare.app, name="prepare", help="Prepare files needed for an analysis.")
app.add_typer(importer.app, name="import", help="Import files into database.")
app.add_typer(export.app, name="export", help="Export tables from database.")


@app.command()
def compute(
    state: str,
    city_shp: pathlib.Path,
    pfb_osm_file: pathlib.Path,
    output_dir: pathlib.Path = common.OutputDir,
    docker_image: typing.Optional[str] = common.DockerImage,
    container_name: typing.Optional[str] = common.ContainerName,
    city_fips: common.FIPSCode = None,
) -> None:
    """Run an analysis."""
    # Make MyPy happy.
    if not docker_image:
        raise ValueError("`docker_image` must be set")

    # Retrieve the state info if needed.
    state_abbrev, state_fips = analysis.state_info(state) if state else ("0", "0")
    if not state_abbrev:
        raise ValueError("`state_abbrev` must be set")
    if not state_fips:
        raise ValueError("`state_fips` must be set")
    compute_(
        state_abbrev,
        state_fips,
        city_shp,
        pfb_osm_file,
        output_dir,
        docker_image,
        container_name,
        city_fips,
    )


# pylint: disable=too-many-arguments,duplicate-code
def compute_(
    state_abbrev: str,
    state_fips: str,
    city_shp: pathlib.Path,
    pfb_osm_file: pathlib.Path,
    output_dir: pathlib.Path,
    docker_image: str,
    container_name: str | None = None,
    city_fips: str | None = None,
) -> None:
    """Run the analysis."""
    console = Console()
    with console.status("[bold green]Running the full analysis (may take a while)..."):
        runner.run_analysis(
            state_abbrev,
            state_fips,
            city_shp,
            pfb_osm_file,
            output_dir,
            docker_image,
            container_name,
            city_fips=city_fips,
        )
        console.log(f"Analysis for {city_shp} complete.")


@app.command()
def run(
    country: str,
    city: str,
    state: typing.Optional[str] = typer.Argument(None),
    output_dir: pathlib.Path = common.OutputDir,
    docker_image: typing.Optional[str] = common.DockerImage,
    speed_limit: typing.Optional[int] = common.SpeedLimit,
    block_size: typing.Optional[int] = common.BlockSize,
    block_population: typing.Optional[int] = common.BlockPopulation,
    container_name: typing.Optional[str] = common.ContainerName,
    city_fips: common.FIPSCode = "0",
    retries: typing.Optional[int] = common.Retries,
) -> None:
    """Prepare all files and run an analysis."""
    # Make MyPy happy.
    if not docker_image:
        raise ValueError("`docker_image` must be set")
    if not speed_limit:
        raise ValueError("`speed_limit` must be set")
    if not block_size:
        raise ValueError("`block_size` must be set")
    if not block_population:
        raise ValueError("`block_population` must be set")
    if not retries:
        raise ValueError("`retries` must be set")

    # Prepare and run.
    asyncio.run(
        prepare_and_run(
            country,
            state,
            city,
            output_dir,
            docker_image,
            speed_limit,
            block_size,
            block_population,
            container_name,
            city_fips,
            retries,
        )
    )


# pylint: disable=too-many-arguments
async def prepare_and_run(
    country: str,
    state: str | None,
    city: str,
    output_dir: pathlib.Path,
    docker_image: str,
    speed_limit: int,
    block_size: int,
    block_population: int,
    container_name: str | None,
    city_fips: str | None,
    retries: int,
) -> None:
    """Prepare all files and run an analysis."""
    speed_file = output_dir / "city_fips_speed.csv"
    speed_file.unlink(missing_ok=True)
    tabblock_file = output_dir / "tabblock2010_91_pophu.zip"
    tabblock_file.unlink(missing_ok=True)
    params = await prepare.prepare_(
        country,
        state,
        city,
        output_dir,
        speed_limit,
        block_size,
        block_population,
        retries,
    )
    compute_(*params, docker_image, container_name, city_fips)
