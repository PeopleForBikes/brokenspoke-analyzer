import logging
import pathlib
import sys
import typing
from importlib import resources

import typer
from loguru import logger
from rich.console import Console
from sqlalchemy import create_engine

from brokenspoke_analyzer.cli import (
    common,
    configure,
    export,
    importer,
    prepare,
)
from brokenspoke_analyzer.core import (
    analysis,
    compute,
    constant,
    ingestor,
    utils,
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


@app.command(name="compute")
def compute_cmd(
    database_url: common.DatabaseURL,
    input_dir: common.InputDir,
    country: common.Country,
    city: common.City,
    state: common.State = None,
    buffer: common.Buffer = common.DEFAULT_BUFFER,
) -> None:
    """Run an analysis."""
    # Make MyPy happy.
    if not buffer:
        raise ValueError("`buffer` must be set")

    # Prepare the database connection.
    engine = create_engine(
        database_url.replace("postgresql://", "postgresql+psycopg://")
    )

    # Prepare directories.
    _, slug = analysis.osmnx_query(country, city, state)
    traversable = resources.files("brokenspoke_analyzer.scripts.sql")
    res = pathlib.Path(traversable._paths[0])  # type: ignore
    sql_script_dir = res.resolve(strict=True)
    boundary_file = input_dir / f"{slug}.shp"

    # Prepare compute params.
    state_default_speed, city_default_speed = ingestor.retrieve_default_speed_limits(
        engine
    )
    tolerance = compute.Tolerance()
    path_constraint = compute.PathConstraint()
    block_road = compute.BlockRoad()
    score = compute.Score()
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
            tolerance=tolerance,
            path_constraint=path_constraint,
            block_road=block_road,
            score=score,
            import_jobs=import_jobs,
        )
        console.log(f"Analysis for {slug} complete.")


@app.command()
def run(
    database_url: common.DatabaseURL,
    country: common.Country,
    city: common.City,
    state: common.State = None,
    output_dir: typing.Optional[pathlib.Path] = common.OutputDir,
    fips_code: common.FIPSCode = "0",
    buffer: common.Buffer = common.DEFAULT_BUFFER,
    speed_limit: typing.Optional[int] = common.SpeedLimit,
    block_size: typing.Optional[int] = common.BlockSize,
    block_population: typing.Optional[int] = common.BlockPopulation,
    census_year: common.CensusYear = common.DEFAULT_CENSUS_YEAR,
    retries: typing.Optional[int] = common.Retries,
    max_trip_distance: typing.Optional[int] = 2680,
) -> None:
    """Run an analysis."""
    # Make mypy happy.
    if not output_dir:
        raise ValueError("`output_dir` must be set")

    # Prepare the database connection.
    engine = create_engine(
        database_url.replace("postgresql://", "postgresql+psycopg://")
    )

    # Prepare.
    logger.info("Prepare")
    prepare.all(
        country=country,
        city=city,
        state=state,
        fips_code=fips_code,
        output_dir=output_dir,
        speed_limit=speed_limit,
        block_size=block_size,
        block_population=block_population,
        retries=retries,
    )

    # Import.
    logger.info("Import")
    _, slug = analysis.osmnx_query(country, city, state)
    input_dir = output_dir / slug
    importer.all(
        database_url=database_url,
        input_dir=input_dir,
        country=country,
        city=city,
        state=state,
        census_year=census_year,
        buffer=buffer,
    )

    # Compute.
    logger.info("Compute")
    traversable = resources.files("brokenspoke_analyzer.scripts.sql")
    res = pathlib.Path(traversable._paths[0])  # type: ignore
    sql_script_dir = res.resolve(strict=True)
    boundary_file = input_dir / f"{slug}.shp"
    output_srid = utils.get_srid(boundary_file.resolve(strict=True))
    state_default_speed, city_default_speed = ingestor.retrieve_default_speed_limits(
        engine
    )
    if country.upper() == "US":
        country = "usa"
    import_jobs = country.upper() == constant.COUNTRY_USA

    compute.all(
        database_url=database_url,
        sql_script_dir=sql_script_dir,
        output_srid=output_srid,
        buffer=buffer,
        state_default_speed=state_default_speed,
        city_default_speed=city_default_speed,
        tolerance=compute.Tolerance(),
        path_constraint=compute.PathConstraint(),
        block_road=compute.BlockRoad(),
        score=compute.Score(),
        import_jobs=import_jobs,
        max_trip_distance=max_trip_distance,
    )

    # Export.
    logger.info("Export")
    export.local_calver(
        database_url=database_url,
        country=country,
        city=city,
        region=state,
        force=False,
        export_dir=input_dir / "results",
    )
