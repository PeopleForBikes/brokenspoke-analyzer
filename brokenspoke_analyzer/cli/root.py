"""Define the top-level commands."""
import logging
import pathlib
import typing
from importlib import (
    metadata,
    resources,
)

import typer
from loguru import logger
from rich.console import Console
from rich.logging import RichHandler
from typing_extensions import Annotated

from brokenspoke_analyzer.cli import (
    common,
    configure,
    export,
    importer,
    prepare,
    run_with,
)
from brokenspoke_analyzer.core import (
    analysis,
    compute,
    constant,
    exporter,
    ingestor,
    utils,
)
from brokenspoke_analyzer.core.database import dbcore


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


def _version_callback(value: bool) -> None:
    """Get the package's version."""
    package_version = metadata.version("brokenspoke-analyzer")
    if value:
        typer.echo(f"brokenspoke-analyzer version: {package_version}")
        raise typer.Exit()


# Create the CLI app.
app = typer.Typer()


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


app.add_typer(
    configure.app, name="configure", help="Configure a database for an analysis."
)
app.add_typer(prepare.app, name="prepare", help="Prepare files needed for an analysis.")
app.add_typer(importer.app, name="import", help="Import files into database.")
app.add_typer(export.app, name="export", help="Export tables from database.")
app.add_typer(run_with.app, name="run-with", help="Run an analysis in different ways.")


@app.command(name="compute")
def compute_cmd(
    database_url: common.DatabaseURL,
    input_dir: common.InputDir,
    country: common.Country,
    city: common.City,
    region: common.Region = None,
    buffer: common.Buffer = common.DEFAULT_BUFFER,
) -> None:
    """Run an analysis."""
    # Make MyPy happy.
    if not buffer:
        raise ValueError("`buffer` must be set")

    # Prepare the database connection.
    engine = dbcore.create_psycopg_engine(database_url)

    # Prepare directories.
    _, slug = analysis.osmnx_query(country, city, region)
    traversable = resources.files("brokenspoke_analyzer.scripts.sql")
    res = pathlib.Path(traversable._paths[0])  # type: ignore
    sql_script_dir = res.resolve(strict=True)
    boundary_file = input_dir / f"{slug}.shp"

    # Prepare compute params.
    state_default_speed, city_default_speed = ingestor.retrieve_default_speed_limits(
        engine
    )
    if country.upper() == "US":
        country = "usa"
    import_jobs = country.upper() == constant.COUNTRY_USA

    # Compute the output SRID from the boundary file.
    output_srid = utils.get_srid(boundary_file.resolve(strict=True))
    logger.debug(f"{output_srid=}")

    console = Console()
    with console.status("[bold green]Running the full analysis (may take a while)..."):
        compute.all(
            database_url=database_url,
            sql_script_dir=sql_script_dir,
            output_srid=output_srid,
            buffer=buffer,
            state_default_speed=state_default_speed,
            city_default_speed=city_default_speed,
            import_jobs=import_jobs,
        )
        console.log(f"Analysis for {slug} complete.")


@app.command()
def run(
    database_url: common.DatabaseURL,
    country: common.Country,
    city: common.City,
    region: common.Region = None,
    output_dir: common.OutputDir = common.DEFAULT_OUTPUT_DIR,
    fips_code: common.FIPSCode = common.DEFAULT_CITY_FIPS_CODE,
    buffer: common.Buffer = common.DEFAULT_BUFFER,
    city_speed_limit: common.SpeedLimit = common.DEFAULT_CITY_SPEED_LIMIT,
    block_size: common.BlockSize = common.DEFAULT_BLOCK_SIZE,
    block_population: common.BlockPopulation = common.DEFAULT_BLOCK_POPULATION,
    lodes_year: common.LODESYear = common.DEFAULT_LODES_YEAR,
    retries: common.Retries = common.DEFAULT_RETRIES,
    max_trip_distance: common.MaxTripDistance = common.DEFAULT_MAX_TRIP_DISTANCE,
    with_export: typing.Optional[exporter.Exporter] = exporter.Exporter.local,
    s3_bucket: Annotated[
        typing.Optional[str], typer.Option(help="S3 bucket name where to export")
    ] = None,
) -> None:
    """Run an analysis."""
    run_with.run_(
        database_url=database_url,
        country=country,
        city=city,
        region=region,
        output_dir=output_dir,
        fips_code=fips_code,
        buffer=buffer,
        city_speed_limit=city_speed_limit,
        block_size=block_size,
        block_population=block_population,
        lodes_year=lodes_year,
        retries=retries,
        max_trip_distance=max_trip_distance,
        with_export=with_export,
        s3_bucket=s3_bucket,
    )
