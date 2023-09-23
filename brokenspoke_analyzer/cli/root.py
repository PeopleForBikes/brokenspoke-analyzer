import logging
import pathlib
import sys
from importlib import resources

import typer
from loguru import logger
from rich.console import Console

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
    ingestor,
    utils,
)
from brokenspoke_analyzer.core.database import dbcore


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
    census_year: common.CensusYear = common.DEFAULT_CENSUS_YEAR,
    retries: common.Retries = common.DEFAULT_RETRIES,
    max_trip_distance: common.MaxTripDistance = common.DEFAULT_MAX_TRIP_DISTANCE,
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
        census_year=census_year,
        retries=retries,
        max_trip_distance=max_trip_distance,
    )
